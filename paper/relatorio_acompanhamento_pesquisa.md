# Relatório de desenvolvimento da pesquisa

## Rastreabilidade entre especificações OpenSpec e código

### Quando uma referência de caminho não resolvida sinaliza fricção de implementação?

**Pesquisador:** Pedro Odorize  
**Projeto:** MSR 2027 Mining Challenge — SpecMine / OpenSpec  
**Data:** 10 de outubro de 2026  
**Finalidade:** documento de acompanhamento para discussão com a orientadora  
**Status:** análise estrutural concluída; validação semântica executada e adjudicada em 90 casos.

> Este documento não é o paper final. Ele registra o que foi feito, o que os resultados significam, quais decisões metodológicas foram tomadas e quais resultados devem ser transferidos para o paper.

---

## 1. Síntese executiva

A pesquisa investiga se características observáveis de artefatos de *Spec-Driven Development* (SDD) estão associadas a sinais de desalinhamento entre especificação e código. O foco foi delimitado para arquivos `tasks.md` do ecossistema OpenSpec, usando o dataset SpecMine. A unidade inicial é uma referência a um caminho de código encontrada em uma tarefa.

O primeiro resultado importante foi metodológico: `exists_at_anchor = 0` informa que o caminho literal não foi resolvido no snapshot do repositório, mas não prova que existe defeito de implementação. A referência pode ser:

- um arquivo que a tarefa ainda pretende criar;
- um arquivo que será movido, renomeado ou removido;
- um glob ou padrão;
- uma biblioteca ou recurso externo;
- um placeholder ou exemplo documental;
- uma referência ambígua;
- um caminho realmente ausente em uma tarefa que deveria ter sido implementada.

### Conclusão provisória

Há associação entre a estrutura das specs e a presença de referências literais não resolvidas. Porém, a interpretação semântica precisa ser calibrada antes de afirmar que elas representam fricção de implementação.

### Contribuição pretendida

Propor e avaliar uma taxonomia reproduzível para distinguir caminho existente, ausência problemática, ausência esperada, referência não-arquivo, caso ambíguo e caso inacessível, combinando análise em escala com validação humana e uma condição independente de LLM-as-a-judge.

---

## 2. Evolução da pergunta de pesquisa

A hipótese inicial era:

> Em SDD, tamanho da lista de tarefas, densidade de referências a código e taxa de conclusão predizem maior risco de referências a arquivos inexistentes.

Essa formulação tratava implicitamente “arquivo não resolvido” como “implementação problemática”. A inspeção de exemplos mostrou que essa equivalência não é defensável. Uma tarefa aberta que pede criar `goap-planner-service.ts` deve apontar para um arquivo que ainda não existe; uma tarefa de remoção pode apontar para um arquivo ausente porque a remoção era justamente o resultado esperado.

A investigação passou a ter duas camadas:

1. **Camada automática:** detectar e modelar referências literais resolvidas ou não resolvidas.
2. **Camada semântica:** decidir o significado da ausência em cada contexto.

Essa separação é central para a validade do paper.

| Elemento | Formulação atual |
|---|---|
| Objeto | Referências de código em tarefas OpenSpec, não specs em abstrato. |
| Sinal automático | `exists_at_anchor` e resolução do caminho literal no snapshot. |
| Constructo semântico | Existe, ausência problemática, ausência esperada, não-arquivo ou ambiguidade. |
| Preditores | Número de tarefas, densidade, conclusão, tamanho e controles. |
| Claim permitido | Associação e capacidade de triagem; não causalidade nem prova de código ruim. |

---

## 3. Preparação do ambiente: passo a passo

### 3.1 Criação do projeto

Foi criado um repositório Git local para manter o histórico da pesquisa e permitir recuperar versões anteriores de scripts, protocolos e resultados.

```text
msr2027-specmine/
├── analysis/
├── data/raw/
├── data/interim/
├── notebooks/
├── paper/
├── results/
├── src/
├── validation/
├── pyproject.toml
├── uv.lock
└── .python-version
```

O primeiro commit registrou o ambiente reprodutível. Depois foram registrados o protocolo de validação e o fluxo de validação consciente do caminho resolvido.

### 3.2 Ambiente Python

Foi fixado Python 3.12 e criado um ambiente virtual. As dependências ficam registradas em `pyproject.toml` e `uv.lock`, evitando depender de instalações globais.

Ferramentas principais:

- DuckDB e leitura colunar para consultar Parquet;
- Polars para manipulação de tabelas;
- PyArrow para leitura e gravação Parquet;
- Statsmodels para modelos estatísticos;
- `langdetect` para filtrar a amostra confirmatória em inglês;
- Python para scripts, amostragem e planilhas.

### 3.3 Organização dos dados

- `data/raw/`: arquivos originais baixados do SpecMine;
- `data/interim/`: amostras, agregações, features e planilhas geradas;
- `results/`: resultados e figuras finais;
- `validation/`: protocolo e prompt de classificação;
- `paper/`: documentos e versão do paper.

Os arquivos brutos não são editados. Qualquer transformação deve ser reproduzida por script.

### 3.4 Download dos dados

Foram baixados:

```text
data/raw/openspec_code_refs.parquet
data/raw/openspec_artifact_files.parquet
```

O primeiro tem aproximadamente 10 MB; o segundo, aproximadamente 400 MB.

---

## 4. Dados utilizados

### 4.1 Tabela de referências

| Campo | Significado |
|---|---|
| `id` | Identificador da referência. |
| `repo_name` | Repositório de origem. |
| `artifact_path` | Caminho do artefato OpenSpec. |
| `code_path` | Caminho literal citado na tarefa. |
| `task_done` | Tarefa marcada como concluída ou aberta. |
| `anchor_sha` | Commit usado como referência. |
| `exists_at_anchor` | Resultado automático da resolução. |
| `resolved_path` | Caminho resolvido, quando disponível. |

### 4.2 Tabela de artefatos

| Campo | Significado |
|---|---|
| `repo_name` | Repositório. |
| `file_path` | Localização do artefato. |
| `kind` | Tipo, principalmente `tasks.md`. |
| `content` | Conteúdo textual. |
| `n_tasks` | Número de tarefas. |
| `n_tasks_done` | Tarefas concluídas. |
| `n_code_refs` | Referências de código. |
| `n_bytes` | Tamanho textual. |

### 4.3 Desfecho automático inicial

Foram analisados separadamente:

- `exists_at_anchor = 1`: caminho literal resolvido;
- `exists_at_anchor = 0`: caminho literal não resolvido.

Os valores `2` e nulos foram considerados indeterminados e excluídos da análise binária principal. Essa decisão de mensuração será explicitada no paper.

### 4.4 Como as duas tabelas foram relacionadas

O dataset possui uma tabela em nível de referência e outra em nível de artefato. A referência individual responde “qual caminho foi citado?”, enquanto o artefato responde “em que tipo de documento essa referência apareceu e qual era a estrutura da lista de tarefas?”.

O relacionamento foi feito pelas chaves do artefato, principalmente:

```text
(repo_name, artifact_path)
```

Em termos conceituais:

1. cada linha de `openspec_code_refs` representa uma ocorrência de um caminho citado;
2. o par repositório + caminho do artefato identifica o `tasks.md` de origem;
3. os metadados desse artefato são anexados à referência;
4. as referências são agregadas de volta ao nível do artefato para calcular percentuais e modelos.

Esse desenho evita misturar diretamente medidas em níveis diferentes. Por exemplo, `n_tasks` é uma característica do artefato, enquanto `exists_at_anchor` é uma característica de uma referência individual.

### 4.5 Níveis de análise

Há três níveis diferentes no estudo:

| Nível | Unidade | Exemplos |
|---|---|---|
| Referência | Uma ocorrência de caminho em uma tarefa | `code_path`, `task_done`, `exists_at_anchor` |
| Artefato | Um `tasks.md` | `n_tasks`, `n_tasks_done`, `n_code_refs`, `n_bytes` |
| Repositório | Um projeto GitHub | agrupamento estatístico e concentração |

Uma mesma spec pode ter várias referências; um repositório pode ter várias specs. Por isso, o número de linhas de referência não é igual ao número de artefatos nem ao número de repositórios.

---

## 5. Auditoria do corpus

### 5.1 Resultados de consistência

| Medida | Resultado |
|---|---:|
| Linhas de referência | 435.401 |
| Repositórios | 7.076 |
| Artefatos com tarefas válidas | 60.278 |
| Referências com resolução binária | 413.062 |
| Caminhos resolvidos | 361.083 |
| Caminhos não resolvidos | 51.979 |
| Estados indeterminados ou nulos | 22.339 |
| Matching referência–artefato | 100% |

### 5.2 Distribuição da resolução

| Estado | Quantidade | Percentual |
|---|---:|---:|
| Caminho existe | 361.083 | 82,931% |
| Caminho não existe | 51.979 | 11,938% |
| Indeterminado ou nulo | 22.339 | 5,131% |

O número 51.979 deve ser chamado de “referências literais não resolvidas”, não de “referências problemáticas”.

### 5.3 Como esses números foram calculados

Os totais foram obtidos contando linhas após a leitura dos Parquet e verificando duplicidades e valores ausentes.

- **Linhas de referência:** número de registros do arquivo de referências.
- **Repositórios:** `count(distinct repo_name)`.
- **Caminhos resolvidos:** `count(*)` entre as linhas com `exists_at_anchor = 1`.
- **Caminhos não resolvidos:** `count(*)` entre as linhas com `exists_at_anchor = 0`.
- **Estados indeterminados:** soma das linhas com `exists_at_anchor = 2` ou valor nulo.
- **Percentual:** quantidade da categoria dividida pelo número total de linhas de referência, multiplicada por 100.

Por exemplo:

```text
percentual de caminhos não resolvidos
= 51.979 / 435.401 × 100
= 11,938%
```

Para os modelos binários, o denominador muda: são consideradas somente as 413.062 referências com estado 0 ou 1. Assim, o percentual de 11,938% usa todas as referências, enquanto uma taxa usada em uma tabela de modelagem usa apenas a população binária elegível.

### 5.4 Verificações de qualidade

Foram verificadas:

- existência de identificadores ausentes;
- identificadores duplicados;
- ausência de `repo_name`, `artifact_path` ou `code_path`;
- ausência de `task_done`;
- ausência de `exists_at_anchor`;
- correspondência entre referências e artefatos;
- valores inesperados de `exists_at_anchor`.

O matching entre as referências e os artefatos foi de 100% para as chaves analisadas. Isso significa que cada referência do recorte podia ser ligada a um artefato correspondente no dataset liberado; não significa que cada caminho citado exista no código.

---

## 6. Análise estrutural dos artefatos

Para cada artefato foram calculados:

- `completion_rate = n_tasks_done / n_tasks`;
- `reference_density = n_code_refs / n_tasks`;
- número de tarefas;
- número de referências;
- tamanho em bytes;
- número e percentual de referências não resolvidas;
- grupo de conclusão: nenhuma, parcial ou todas as tarefas concluídas.

### 6.1 Fórmulas e filtros

O modelo estrutural considera artefatos de tarefas com `n_tasks > 0`. Artefatos sem tarefas não permitem calcular uma taxa de conclusão ou uma densidade de referências de maneira interpretável e foram excluídos dessa etapa.

As variáveis foram calculadas assim:

```text
completion_rate = n_tasks_done / n_tasks
reference_density = n_code_refs / n_tasks
```

Quando o artefato tem 20 tarefas e 4 referências, por exemplo:

```text
completion_rate = n_tasks_done / 20
reference_density = 4 / 20 = 0,20
```

Para evitar divisão por zero, artefatos com `n_tasks = 0` não entram no modelo estrutural. A taxa de conclusão foi limitada ao intervalo esperado `[0, 1]` quando os dados permitiam essa verificação.

Para cada artefato também foi calculado:

```text
n_missing = número de referências com exists_at_anchor = 0
n_eligible = número de referências com exists_at_anchor em {0, 1}
missing_rate = n_missing / n_eligible
```

O cálculo por artefato é diferente do percentual global. Um artefato com 1 referência ausente tem `missing_rate = 100%`, mas isso não significa que 100% de todas as referências do corpus sejam ausentes. Por isso, o relatório distingue sempre percentuais agrupados por referência de médias entre artefatos.

### 6.2 Grupos de conclusão

Os grupos foram definidos a partir da taxa de conclusão:

- **nenhuma concluída:** `n_tasks_done = 0`;
- **todas concluídas:** `n_tasks_done = n_tasks`;
- **conclusão parcial:** `0 < n_tasks_done < n_tasks`.

Em cada grupo, o percentual apresentado na seção de resultados é um percentual agrupado por referência:

```text
percentual ausente no grupo
= referências ausentes no grupo / todas as referências elegíveis no grupo × 100
```

Isso explica por que os valores não são necessariamente iguais à média simples das taxas dos artefatos. A média simples daria o mesmo peso a um artefato com uma referência e a outro com centenas de referências.

### 6.3 Distribuições observadas

| Variável | Mediana | P95 | Máximo |
|---|---:|---:|---:|
| Número de tarefas | 20 | 71 | 964 |
| Referências de código | 4 | 22 | 60 |
| Taxa de conclusão | 1,00 | — | — |
| Densidade de referências | 0,225 | 0,800 | 12,000 |
| Tamanho em bytes | 2.957 | 12.161 | 849.322 |

A mediana de conclusão igual a 1,00 mostra que muitas specs estão arquivadas ou marcadas como completas. Mesmo entre tarefas concluídas há referências literais não resolvidas.

---

## 7. Resultados preliminares

### 7.1 Ausências por grupo de conclusão

| Grupo | Referências | Não resolvidas | Percentual |
|---|---:|---:|---:|
| Nenhuma tarefa concluída | 32.804 | 9.096 | 27,73% |
| Conclusão parcial | 98.398 | 15.684 | 15,94% |
| Todas concluídas | 276.988 | 26.434 | 9,54% |

Maior conclusão está associada a menor proporção de ausência literal. Isso pode refletir intenção futura em tarefas abertas, mas não decide o significado de cada caso.

### 7.1.1 Como a tabela foi construída

Para cada referência elegível, foi mantido o grupo de conclusão do artefato ao qual ela pertence. Depois foram contadas, dentro de cada grupo:

```text
n_references = todas as referências com estado 0 ou 1
n_missing = referências com estado 0
pct_missing = n_missing / n_references × 100
```

Por exemplo, para o grupo “todas concluídas”:

```text
26.434 / 276.988 × 100 = 9,54%
```

O cálculo é feito no nível de referência porque a pergunta nessa tabela é: “entre as referências desse grupo, qual fração não foi resolvida?”.

### 7.2 Modelo logístico exploratório

O desfecho foi `1` para referência não resolvida e `0` para referência resolvida. O modelo foi agrupado por repositório.

### 7.2.1 Como o modelo foi montado

O conjunto analítico do modelo contém referências binárias ligadas a artefatos com tarefas válidas. Cada linha recebe:

- `y = 1` se `exists_at_anchor = 0`;
- `y = 0` se `exists_at_anchor = 1`;
- `log_tasks = log(n_tasks)`;
- `reference_density_z`, a densidade padronizada;
- `log_bytes = log(n_bytes)`;
- indicadores para conclusão parcial e nenhuma concluída, usando “todas concluídas” como referência.

O logaritmo reduz a influência de artefatos extremos, como uma spec com 964 tarefas. A padronização da densidade coloca essa variável em escala comparável e faz o odds ratio representar uma mudança de um desvio-padrão.

Em forma simplificada, o modelo estima:

```text
logit(P(y = 1))
= intercepto
  + β1 log_tasks
  + β2 reference_density_z
  + β3 log_bytes
  + β4 partial_complete
  + β5 none_complete
```

O odds ratio de cada preditor é `exp(β)`. Um OR maior que 1 indica aumento da chance relativa do desfecho; um OR menor que 1 indica redução. O intervalo de confiança informa a incerteza da estimativa.

O agrupamento por repositório é importante porque referências do mesmo projeto não são observações totalmente independentes. Specs do mesmo repositório podem compartilhar convenções, autores, ferramentas e histórico.

O modelo ainda é exploratório: ele não controla todos os possíveis fatores de confusão e usa o desfecho automático, não o rótulo semântico validado.

| Preditor | Odds ratio | IC 95% | p |
|---|---:|---:|---:|
| `log(número de tarefas)` | 1,538 | 1,369–1,727 | < 0,001 |
| Densidade padronizada | 1,035 | 1,001–1,070 | 0,047 |
| `log(tamanho em bytes)` | 1,028 | 0,911–1,159 | 0,657 |
| Conclusão parcial vs. completa | 1,463 | 1,314–1,629 | < 0,001 |
| Nenhuma concluída vs. completa | 3,191 | 2,701–3,770 | < 0,001 |

O resultado mais estável foi o número de tarefas. Isso indica associação estrutural, não causalidade.

### 7.3 Robustez

No recorte de referências de tarefas concluídas:

- `log(número de tarefas)`: OR 1,510, IC 95% 1,304–1,749;
- conclusão parcial vs. completa: OR 1,252, IC 95% 1,128–1,390;
- densidade e tamanho: não significativos.

Removendo os 50 repositórios mais concentrados, o número de tarefas continuou associado ao desfecho: OR 1,480, IC 95% 1,259–1,739.

---

## 8. Análise da forma textual dos caminhos

Uma classificação lexical simples separou caminho relativo, glob, fragmento/extensão, caminho relativo ao projeto e nome de arquivo isolado.

Entre referências não resolvidas de tarefas concluídas:

| Forma | Participação | Resolução observada |
|---|---:|---:|
| Caminho relativo ao projeto | 53,55% | 92,01% resolvem; os demais exigem interpretação |
| Nome de arquivo isolado | 38,82% | 86,65% resolvem; pode haver ambiguidade |
| Glob/padrão | 4,66% | 4,49% resolvem; frequentemente não é arquivo literal |
| Fragmento/extensão | 2,36% | 0% resolvem; candidato a não-arquivo ou placeholder |

A forma textual ajuda a detectar ruído, mas não substitui a leitura do contexto.

### 8.1 Como a forma textual foi extraída

Cada `code_path` foi normalizado apenas para a análise lexical, preservando também o valor original para auditoria. Foram procurados padrões simples:

- presença de `*`, `?` ou colchetes: provável glob/padrão;
- presença de extensão isolada ou fragmento curto: provável referência incompleta;
- prefixos relativos como `./` ou `../`;
- caminhos com vários componentes separados por `/`: provável caminho relativo ao projeto;
- nome simples sem diretório: possível nome de arquivo isolado.

Essa etapa não decide a categoria semântica. Ela serve para responder uma pergunta auxiliar: “quais formatos aparecem com maior frequência entre as referências não resolvidas?”.

Os percentuais da tabela usam como denominador todas as referências não resolvidas dentro do grupo indicado. Já a “resolução observada” usa o conjunto de todas as referências que apresentam aquela forma, permitindo comparar a frequência de resolução entre formas.

---

## 9. Validade de constructo

O constructo de interesse é “fricção na passagem da especificação para o código”. O dataset fornece diretamente apenas um sinal mais simples: o caminho literal foi ou não encontrado no commit âncora.

A pesquisa precisa mostrar como esse sinal pode ser usado sem confundí-lo com o constructo completo.

### Taxonomia proposta

| Categoria | Critério |
|---|---|
| `confirmed_exists` | O caminho local existe no commit verificável. |
| `confirmed_missing_problematic` | O caminho local deveria existir no contexto, mas está ausente sem explicação de criação, movimento ou remoção. |
| `expected_absence_create` | A tarefa aberta pede criar ou adicionar o arquivo. |
| `expected_absence_move_or_delete` | A tarefa pede remover, mover, renomear, substituir ou deprecar o caminho. |
| `non_file_reference` | Biblioteca, URL, glob, extensão, placeholder ou exemplo documental. |
| `ambiguous_reference` | Não há contexto suficiente para decidir com segurança. |
| `inaccessible_or_invalid` | Repositório, commit ou caminho não pode ser verificado. |

### Regra de decisão refinada

1. Verificar se a string representa arquivo local, biblioteca, recurso externo, glob ou exemplo.
2. Se não for arquivo local, usar `non_file_reference`.
3. Se for local e existir, usar `confirmed_exists`.
4. Se for local e estiver ausente, verificar a intenção:
   - criação/adicionar: `expected_absence_create`;
   - mover/renomear/remover/substituir: `expected_absence_move_or_delete`;
   - atualização, correção ou teste de algo que deveria existir: `confirmed_missing_problematic`;
   - contexto insuficiente: `ambiguous_reference`.
5. Se a evidência não for acessível, usar `inaccessible_or_invalid`.

Na dúvida, a regra é não transformar incerteza em falso problema: classificar como ambíguo ou inacessível.

---

## 10. Validação semântica: execução e adjudicação

### 10.1 Protocolo

Foi criado `validation/PROTOCOL.md`, com objetivo, categorias, instruções e campos de auditoria. O prompt e o schema da LLM foram congelados antes da execução. A regra de decisão dá precedência a referências que não são arquivos, criação explícita e movimentação/remoção antes de considerar uma ausência problemática.

### 10.2 Piloto

Foi criado um piloto estratificado de 60 casos:

- 20 abertas + ausente;
- 20 concluídas + ausente;
- 20 concluídas + existe.

O piloto serviu para descobrir dificuldades de interpretação; não é o ground truth final.

### 10.2.1 Como a amostra foi selecionada

A amostragem foi estratificada para garantir que os três grupos relevantes aparecessem em quantidades iguais. O procedimento foi:

1. filtrar referências para o estrato desejado;
2. remover estados indeterminados;
3. remover casos já usados no piloto e na amostra anterior;
4. selecionar candidatos com semente aleatória fixa;
5. recuperar o trecho da tarefa e as URLs de auditoria;
6. aplicar o filtro de idioma;
7. manter 30 casos por estrato.

A semente fixa torna a seleção reproduzível. O filtro em inglês não foi usado para alterar as taxas do corpus; foi usado apenas para tornar possível uma avaliação humana consistente na etapa de calibração.

### 10.3 Amostra confirmatória em inglês

Como alguns casos anteriores estavam em idiomas que não podiam ser avaliados com segurança, foi criada uma amostra nova e independente:

- 30 abertas + ausente;
- 30 concluídas + ausente;
- 30 concluídas + existe;
- total de 90 casos;
- sem sobreposição com o piloto;
- filtragem por idioma com alta probabilidade de inglês;
- sem scripts estrangeiros no trecho analisado.

Arquivos principais da amostra:

```text
data/interim/validation_human_fresh_90_en.csv
data/interim/validation_human_fresh_90_en.xlsx
data/interim/validation_human_fresh_90_en_key.csv
data/interim/validation_human_fresh_90_en_manifest.json
data/interim/llm_judge_inputs_human_90.jsonl
```

### 10.4 Planilha

A planilha editável é:

```text
data/interim/validation_human_fresh_90_en.xlsx
```

Ela possui as abas `Review` e `Guide`, URLs, contexto da tarefa, caminho literal, caminho resolvido, classificação, nota de evidência e campo de problema de acesso. As células de preenchimento estão destacadas e a classificação possui opções controladas.

Os 90 rótulos humanos de primeira passagem foram preenchidos por R1 e congelados em `data/interim/validation_human_fresh_90_R1_initial.csv`. Quatro casos receberam `inaccessible_or_invalid` porque a evidência necessária não estava acessível. Esses rótulos iniciais não foram tratados como gold standard definitivo.

### 10.5 Execução independente da LLM

A LLM foi executada em todos os 90 casos antes da adjudicação humana. Cada caso foi enviado a um processo efêmero e isolado, com configuração limpa, sandbox somente leitura e apenas o registro congelado, o prompt e o schema JSON. O modelo não recebeu as respostas humanas, as justificativas, os problemas de acesso ou os estratos privados da amostra.

Configuração registrada:

| Elemento | Valor |
|---|---|
| Modelo | `gpt-6-sol` |
| Esforço de raciocínio | `low` |
| Processos independentes | 1 por caso |
| Saídas válidas | 90/90 |
| CLI | `codex-cli 0.157.1` |
| Prompt | `validation/LLM_JUDGE_PROMPT.md` |

Os resultados brutos e o manifesto da execução foram preservados em `data/interim/llm_human_90_raw/`, `data/interim/llm_human_90_results.csv` e `data/interim/llm_human_90_run_manifest.json`.

### 10.6 Comparação pré-adjudicação

Na primeira comparação, os 90 rótulos de R1 foram usados apenas como referência provisória:

| População | Concordância exata | Cohen's κ | Macro-F1 | Discordâncias |
|---|---:|---:|---:|---:|
| Subconjunto semântico, 86 casos | 66/86 (76,7%) | 0,691 | 0,674 | 20 |
| Todos os casos, 90 | 66/90 (73,3%) | 0,653 | 0,566 | 24 |

O subconjunto semântico exclui os quatro casos `inaccessible_or_invalid`, pois R1 pôde tentar acessar URLs ao passo que a LLM recebeu apenas o registro congelado. Os intervalos de confiança foram estimados por 5.000 reamostragens bootstrap em nível de caso.

As divergências mais frequentes foram:

- oito casos em que R1 marcou `confirmed_exists` e a LLM marcou `expected_absence_create`;
- cinco casos em que R1 marcou `confirmed_missing_problematic` e a LLM marcou `ambiguous_reference`.

Esse padrão revelou uma tensão real do protocolo: a ação descrita na tarefa pode indicar criação futura mesmo quando o caminho resolvido aponta para um arquivo que já existe no commit analisado.

### 10.7 Adjudicação humana

As 24 divergências foram devolvidas a R1 em uma planilha separada. A adjudicação exibiu os dois rótulos, as evidências e as justificativas, mas preservou os rótulos iniciais em colunas imutáveis. R1 preencheu uma classificação final, uma justificativa e a origem da decisão para cada caso.

Resultado da adjudicação:

- 24/24 casos preenchidos e validados;
- cinco rótulos iniciais alterados;
- 19 rótulos iniciais mantidos, com rejeição da proposta da LLM;
- nenhum campo imutável alterado.

Os cinco casos alterados foram: quatro referências que passaram de ausência problemática para `non_file_reference` e uma referência que passou de `ambiguous_reference` para `confirmed_missing_problematic`. Isso reforça que a ausência literal pode ser explicada por outro repositório, um artefato de design externo ou uma refatoração anterior.

### 10.8 Comparação final contra os rótulos adjudicados

Os rótulos finais adjudicados são a referência principal do paper. Os rótulos de primeira passagem permanecem como análise de sensibilidade e não são sobrescritos.

| População | Concordância exata | Cohen's κ | Macro-F1 | Discordâncias |
|---|---:|---:|---:|---:|
| Subconjunto semântico, 86 casos | 66/86 (76,7%) | 0,691 | 0,673 | 20 |
| Taxonomia colapsada, 86 casos | 71/86 (82,6%) | 0,732 | 0,772 | 15 |
| Todos os casos, 90 | 66/90 (73,3%) | 0,653 | 0,559 | 24 |
| Taxonomia colapsada, 90 | 71/90 (78,9%) | 0,687 | 0,590 | 19 |

O fato de a concordância exata não ter aumentado após a adjudicação não significa que a adjudicação foi inútil. R1 alterou cinco rótulos por razões substantivas, mas essas alterações se afastaram das propostas da LLM. A adjudicação melhorou a validade interpretativa do conjunto de referência; a taxonomia colapsada mostra esse efeito com maior estabilidade.

### 10.9 Prevalência semântica calibrada

A amostra de 90 casos foi balanceada por desenho: 30 casos em cada estrato. Por isso, não é correto usar diretamente a fração de rótulos `confirmed_missing_problematic` da amostra como prevalência do corpus. Para obter uma estimativa exploratória, os dois estratos com ausência literal foram reponderados pelo número de referências existentes no Parquet original.

| Estrato | População | Amostra | Problemáticas | Taxa conservadora | Taxa conhecida |
|---|---:|---:|---:|---:|---:|
| concluída + ausente | 34.227 | 30 | 3 | 10,0% | 10,0% |
| aberta + ausente | 17.752 | 30 | 2 | 6,7% | 7,4% |

Na taxa conservadora, os três casos inacessíveis do estrato aberto são mantidos no denominador e tratados como não problemáticos. Na análise de sensibilidade conhecida, esses casos são retirados do denominador. A estimativa ponderada de referências literalmente não resolvidas que são semanticamente problemáticas é:

- **8,9%** na análise conservadora, com intervalo bootstrap de 95% entre **2,2% e 17,6%**;
- **9,1%** na análise conhecida, com intervalo bootstrap de 95% entre **2,2% e 17,8%**.

Esses valores não significam que aproximadamente 9% das specs têm defeitos. O estimando é mais estreito: a fração de referências de código com `exists_at_anchor = 0` que, após leitura contextual, permanece classificada como ausência problemática. A estimativa é exploratória, pois usa um único avaliador, 30 casos por estrato e uma amostra em inglês. Ela serve para calibrar a interpretação do sinal estrutural, não para substituir uma anotação completa do corpus.

### 10.10 Comparação entre GPT-6 Sol e GPT-6 Luna

Para avaliar se um modelo mais barato poderia substituir o modelo utilizado na primeira rodada, os mesmos 90 registros foram enviados ao GPT-6 Luna, sem alterar prompt, schema, dados de entrada ou isolamento. O resultado foi comparado com o GPT-6 Sol e com os rótulos humanos finais.

| Modelo | Concordância semântica | κ | Macro-F1 | F1 binário para ausência problemática |
|---|---:|---:|---:|---:|
| GPT-6 Sol | 66/86 (76,7%) | 0,691 | 0,673 | 0,600 |
| GPT-6 Luna | 61/86 (70,9%) | 0,626 | 0,573 | 0,333 |
| GPT-6 Astra | 64/86 (74,4%) | 0,664 | 0,692 | 0,600 |

Na decisão binária de interesse, considerando 57 casos acessíveis dos dois estratos com ausência literal, o Sol obteve precisão 0,60 e recall 0,60. O Luna obteve precisão 0,286 e recall 0,40, produzindo mais falsos positivos. Em comparação pareada nos 90 casos, os dois modelos acertaram juntos 54 casos; o Sol acertou sozinho 12, enquanto o Luna acertou sozinho 7.

Assim, o GPT-6 Astra não apresentou ganho sobre o GPT-6 Sol nesta amostra: foi ligeiramente inferior na concordância exata e empatou na decisão binária principal. O GPT-6 Luna é uma alternativa economicamente atraente, mas não deve substituir o GPT-6 Sol na análise principal sem uma nova calibração. Ele pode ser usado em uma condição secundária ou como filtro inicial, encaminhando casos ambíguos para o modelo mais forte.

### 10.11 Piloto com evidência equivalente

Para verificar se a diferença entre humano e LLM era causada pela falta de acesso à evidência, foi criado um pacote de commit para dez casos: três `completed + exists`, três `completed + missing` e quatro `open + missing`. Cada pacote continha o contexto da tarefa, o status do caminho literal no SHA do commit, o conteúdo do caminho candidato quando disponível e uma busca por basename na árvore completa do commit. Rótulos humanos, estratos privados e `exists_at_anchor` foram excluídos.

Na primeira versão, que não incluía a busca da árvore completa, Sol acertou 9/10 casos. O único erro foi H004, classificado como ambíguo porque a LLM não podia saber se o arquivo existia em outro diretório. Após incluir a evidência da árvore, Sol classificou H004 corretamente. O piloto refinado obteve **10/10**, κ = **1,000** e Macro-F1 = **1,000**.

Esse resultado é promissor, mas não é uma estimativa final de desempenho: dez casos são insuficientes e não foram selecionados para estimar prevalência. Ele justifica repetir o protocolo de evidência equivalente nos 90 casos antes de qualquer extrapolação para o corpus completo.

### 10.12 Comparação completa com evidência equivalente

O protocolo refinado foi aplicado aos 90 casos. A LLM recebeu o contexto da tarefa, observações dos caminhos fixadas no SHA do commit, conteúdo de caminhos candidatos e busca por basename na árvore do commit. Três casos permaneceram inacessíveis, coincidindo com os casos marcados como inacessíveis pelo avaliador humano.

| Condição | Concordância semântica | κ | Macro-F1 |
|---|---:|---:|---:|
| Sol, registro congelado, n=86 | 76,7% | 0,691 | 0,673 |
| Sol, evidência equivalente, n=86 | **80,2%** | **0,738** | 0,678 |

No conjunto completo, a condição de evidência equivalente obteve 70/90 (77,8%) de concordância, κ = 0,711 e Macro-F1 = 0,631. O aumento em relação ao registro congelado confirma que parte da discordância anterior era causada por assimetria de informação.

No desfecho binário, considerando 57 casos acessíveis dos estratos com ausência literal, o Sol encontrou os cinco casos humanos classificados como `confirmed_missing_problematic` (recall = 1,000), mas produziu seis falsos positivos (precisão = 0,455; F1 = 0,625). Portanto, a LLM é mais adequada como instrumento de triagem de alta sensibilidade do que como fonte de rótulos definitivos.

Esse resultado justifica o uso da LLM em análise exploratória de larga escala, desde que os casos classificados como problemáticos sejam tratados como candidatos e que a estimativa seja acompanhada por calibração, intervalos de incerteza e auditoria humana.

---

## 11. Como a LLM foi usada

A LLM não foi tratada como autoridade final. Ela produziu uma classificação proposta e uma justificativa estruturada; R1 confirmou ou corrigiu somente os casos em que houve divergência.

Fluxo executado:

1. Congelar taxonomia, prompt, modelo e regras.
2. Congelar uma entrada sem vazamento a partir da amostra original.
3. Executar um processo efêmero independente para cada um dos 90 casos.
4. Comparar as 90 propostas com os rótulos humanos de primeira passagem.
5. Reabrir as 24 divergências em uma planilha de adjudicação.
6. Preservar os rótulos iniciais e produzir uma referência final adjudicada.
7. Reportar os resultados finais e manter a comparação pré-adjudicação como análise de sensibilidade.

O desenho não permite interpretar a taxa de concordância como acurácia absoluta de uma autoridade externa. Ele mede concordância com uma referência humana adjudicada, sob uma taxonomia definida e em uma amostra estratificada em inglês.

Devem ser preservados: prompt, modelo, data, entrada, saída bruta, justificativa, rótulo humano, correção e problema de acesso.

---

## 12. Limitações

- Ausência literal não é automaticamente defeito.
- A LLM pode induzir o avaliador na adjudicação; por isso os rótulos humanos iniciais foram coletados antes da exposição às respostas do modelo.
- A amostra em inglês melhora a calibração, mas limita a generalização ao corpus multilíngue.
- A condição `inaccessible_or_invalid` não é comparável em igualdade de informação: R1 pôde abrir URLs, enquanto a LLM recebeu somente o registro congelado.
- Cinco decisões humanas foram alteradas na adjudicação; portanto, o primeiro rótulo humano não deve ser tratado como verdade imutável.
- Commits inacessíveis e URLs 404 não devem ser convertidos automaticamente em ausência problemática.
- Alguns repositórios concentram muitas referências; por isso foram usados agrupamento e análise sem os 50 maiores.
- Os modelos mostram associação, não causalidade.

---

## 13. Perguntas para a orientadora

1. A distinção entre resolução literal e fricção semântica está adequada ao objetivo da dissertação?
2. A taxonomia é objetiva o suficiente para replicação?
3. A avaliação com um único avaliador humano, seguida de adjudicação dos desacordos, é suficiente para o Mining Challenge?
4. Devemos incluir um segundo avaliador em uma pequena fração dos 90 casos?
5. O paper deve restringir a calibração ao inglês ou incluir uma extensão multilíngue?
6. A contribuição deve enfatizar a taxonomia/validade de constructo ou a associação estatística?
7. O melhor termo é “fricção de implementação”, “risco de desalinhamento” ou “sinal de rastreabilidade não resolvida”?

---

## 14. Próximas etapas

| Etapa | Entregável | Critério |
|---|---|---|
| Fechar protocolo | `PROTOCOL.md`, prompt e schema congelados | Categorias e precedência documentadas |
| Rodar LLM | JSONL, respostas brutas e manifesto | 90/90 respostas JSON válidas |
| Avaliação humana | Rótulos iniciais R1 | 90 linhas completas e preservadas |
| Adjudicação | Planilha e CSV finais | 24 divergências revisadas; 5 alterações |
| Calibração | Matrizes, κ, Macro-F1 e análise de erros | Resultados pré e pós-adjudicação separados |
| Prevalência calibrada | `PREVALENCE_REPORT.md`, CSV e JSON | Reponderação por estrato e intervalos bootstrap |
| Análise final | Modelos para ausência literal e problemática | IC, agrupamento e robustez |
| Paper | IEEEtran, 4 páginas + referências | Rascunho completo e reprodutível |

A ordem é deliberada: a validação semântica vem antes de reinterpretar o desfecho e antes de expandir a classificação automática.

---

## 15. Mensagem central para a reunião

> A pesquisa já produziu um resultado empírico consistente: specs com mais tarefas e menor conclusão apresentam mais referências literais não resolvidas. A validação em 90 casos mostrou concordância substancial entre a LLM e a referência humana adjudicada, mas também revelou confusões sistemáticas entre arquivos existentes, arquivos a criar, referências externas e referências ambíguas. Portanto, o resultado defensável do paper é uma associação estrutural acompanhada de uma calibração semântica explícita, não a afirmação de que toda ausência literal representa defeito.

---

## 16. Referências e artefatos

- Agarwal, S.; Singhal, A.; Breaux, T.; Vasilescu, B. *SpecMine: A Large-Scale Corpus of Spec-Driven Development Artifacts*. MSR 2027, preprint arXiv:2608.25202.
- SpecMine dataset, snapshot de julho de 2026. Zenodo DOI: `10.5281/zenodo.22102779`.
- SpecMine official mirror: <https://github.com/shyamagarwal13/specmine-official>.
- Protocolo: `validation/PROTOCOL.md`.
- Prompt: `validation/LLM_JUDGE_PROMPT.md`.
- Rótulos humanos iniciais: `data/interim/validation_human_fresh_90_R1_initial.csv`.
- Planilha de adjudicação: `data/interim/validation_human_90_adjudication_R1_adjudicated.xlsx`.
- Rótulos finais: `data/interim/validation_human_90_R1_adjudicated.csv`.
- Resultados pré-adjudicação: `results/validation/human_90/summary.json`.
- Resultados finais: `results/validation/human_90_adjudicated/final_summary.json`.
- Relatório final: `results/validation/human_90_adjudicated/FINAL_REPORT.md`.
- Prevalência semântica calibrada: `results/validation/human_90_adjudicated/PREVALENCE_REPORT.md`, `stratum_prevalence.csv` e `prevalence_summary.json`.
- Comparação GPT-6 Sol/Luna: `results/validation/model_comparison_90/REPORT.md`.
- Resultados GPT-6 Astra: `data/interim/llm_human_90_astra_results.csv` e `results/validation/human_90_astra_adjudicated/`.
- Piloto de evidência equivalente: `results/validation/evidence_equivalent_pilot_10/REPORT.md`.
- Avaliação completa com evidência equivalente: `results/validation/evidence_equivalent_90/REPORT.md`.
- Dados brutos: `data/raw/openspec_code_refs.parquet` e `data/raw/openspec_artifact_files.parquet`.
