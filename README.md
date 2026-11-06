# WebCrawler em Python

Crawler web concorrente, escrito em Python puro, que respeita o `robots.txt` (incluindo `Crawl-delay`), mantém um intervalo educado entre requisições ao mesmo servidor, elimina URLs duplicadas e limita a profundidade e o número de páginas. Os testes rodam totalmente offline: cada teste sobe um servidor `http.server` local, com páginas, ciclos, redirecionamentos, erros e `robots.txt` sob controle.

## Por que este projeto

Rastrear a web é um problema clássico de entrevistas de system design ("projete um crawler") e de engenharia de dados e busca: exige busca em largura, controle de concorrência, deduplicação, normalização de URLs e, principalmente, boa conduta com os sites visitados. Um crawler que ignora `robots.txt` ou dispara dezenas de requisições por segundo contra um único host é um problema operacional e jurídico. Este projeto mostra como tratar essas preocupações de forma verificável.

## Recursos

- Busca em largura com pool de threads (`--workers`), fila compartilhada e término correto (fila vazia e nenhuma tarefa em andamento).
- `robots.txt`: lido uma vez por host, com regras `Disallow`/`Allow`, regras específicas do user agent e `Crawl-delay`. Semântica da RFC 9309: arquivo ausente (4xx) libera tudo; erro 5xx ou host inalcançável bloqueia tudo.
- Intervalo mínimo entre requisições ao mesmo host (`--delay`), garantido mesmo com vários workers; o maior valor entre `--delay` e `Crawl-delay` prevalece.
- Deduplicação por URL normalizada (esquema e host em minúsculas, porta padrão e fragmento removidos), incluindo o destino de redirecionamentos.
- Limite de profundidade (`--depth`) e de páginas (`--max-pages`).
- Escopo restrito ao host inicial por padrão; hosts extras com `--allow-host`.
- Extração de links com `<base href>`, `rel="nofollow"` e `<meta name="robots" content="nofollow">`.
- Conteúdo que não é HTML é registrado, mas não é interpretado; erros HTTP e de rede viram resultados, não exceções.
- Saída em texto (com indentação por profundidade) ou JSON.

## Como executar

Requer Python 3.8 ou superior. Dentro da pasta do projeto:

```bash
python3 -m web_crawler https://example.com/ --depth 2 --max-pages 50 --workers 4 --delay 1.0
python3 -m web_crawler https://example.com/ --json > resultado.json
python3 -m web_crawler https://example.com/ --allow-host www.example.com
```

Use apenas em sites que você tem permissão para rastrear, e mantenha o `--delay` em um valor razoável. `--ignore-robots` existe para testar contra sites próprios e não deve ser usado em sites de terceiros.

Como biblioteca:

```python
from web_crawler import Crawler

resultados = Crawler("https://example.com/", max_depth=2, delay=1.0).crawl()
for r in resultados:
    print(r.depth, r.status, r.url, r.title)
```

## Como testar

```bash
python3 -m unittest -v
```

Nenhum teste acessa a rede externa. Eles cobrem: normalização e extração de links; limitador de taxa com relógio falso; interpretação do `robots.txt` (regras, `Crawl-delay`, agente específico, 404, 503, host fora do ar); e o crawler completo contra servidores locais: ciclos e auto-referências visitados uma única vez, limite de profundidade e de páginas, `Disallow` respeitado (e `robots.txt` buscado uma só vez), intervalo medido entre requisições, concorrência observada no servidor, hosts externos ignorados, erros 404/500, conteúdo não HTML, redirecionamentos e um site com 60 páginas e 8 workers.

## Decisões de projeto

- **Normalização antes da deduplicação.** Sem ela, `/a`, `/a#topo` e `HTTP://Host:80/a` seriam três visitas. A query string é preservada, pois pode mudar o conteúdo.
- **Marcar como visitado ao agendar, não ao buscar.** O conjunto `seen` é consultado e atualizado sob um lock no momento em que o link é descoberto; assim dois workers nunca enfileiram a mesma URL. `max_pages` limita as URLs agendadas.
- **Término com `Queue.join()`.** Como novas tarefas só são criadas por tarefas em andamento, uma fila vazia sem tarefas pendentes significa que o trabalho acabou. Em seguida, sentinelas encerram as threads.
- **Limitador por reserva de horário.** Cada thread reserva o próximo "slot" do host sob um lock e dorme fora dele. Isso serializa as requisições a um mesmo host sem bloquear hosts diferentes e garante o intervalo mesmo com muitos workers (a vazão por host é 1/delay, independentemente da concorrência). A concorrência só acelera o rastreio de vários hosts ou quando `delay` é zero.
- **Falhar de forma conservadora no `robots.txt`.** Se o arquivo não pode ser lido por erro do servidor, assume-se que o rastreio não é bem-vindo.
- **`urllib` e `html.parser`.** Sem dependências; `urllib.robotparser` interpreta as regras, mas o download passa pelo mesmo cliente (com User-Agent, timeout e limite de 2 MiB por resposta).
- **Complexidade:** O(P + L) em tempo para P páginas e L links, mais as esperas de rede; memória O(P) pelo conjunto de URLs e pelos resultados.
- **Trade-off:** BFS em memória é simples e dá ordem por profundidade, mas não é retomável; um crawler de produção persistiria a fronteira em disco.

## Estrutura de pastas

```
WebCrawler/
├── web_crawler/
│   ├── __init__.py
│   ├── __main__.py
│   ├── crawler.py       # Crawler, PageResult, agendamento e workers
│   ├── fetcher.py       # download HTTP com urllib
│   ├── links.py         # normalização de URLs e extração de links
│   ├── politeness.py    # RobotsCache e HostRateLimiter
│   └── cli.py
├── tests/
│   ├── site.py          # servidor http.server usado pelos testes
│   ├── test_links.py
│   ├── test_politeness.py
│   ├── test_crawler.py
│   └── test_cli.py
├── LICENSE
└── README.md
```

## Limitações conhecidas

- Não executa JavaScript: páginas renderizadas no cliente não são vistas.
- A fronteira de URLs fica na memória e o estado não é persistido; um rastreio interrompido recomeça do zero.
- Não interpreta `sitemap.xml`, cabeçalhos `X-Robots-Tag` nem curingas avançados além do que `urllib.robotparser` suporta.
- O `robots.txt` é guardado em cache durante a execução inteira, sem renovação.
- Sem tratamento de conteúdo duplicado com URLs diferentes (apenas dedup por URL) e sem detecção de armadilhas de rastreio, como calendários infinitos, além dos limites de profundidade e páginas.
- Respostas são lidas por inteiro até 2 MiB; não há streaming nem suporte a compressão além do que o `urllib` oferece.

## Licença

MIT. Veja o arquivo [LICENSE](LICENSE).
