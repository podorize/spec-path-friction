# Auditoria pós-hoc dos seis positivos humanos estáveis

## Resultado

Somente **1 dos 6** casos permaneceu `confirmed_missing_problematic` após inspeção da árvore completa do commit, do contexto da tarefa, do histórico do caminho e de caminhos semanticamente correspondentes. Cinco decisões humanas repetidas não foram sustentadas pela evidência ampliada.

| Caso | Classificação da auditoria | Avaliação do rótulo humano | Mecanismo |
| --- | --- | --- | --- |
| S010 | external_repository_reference | human_not_supported | repository_boundary |
| S015 | expected_absence_move_or_delete | human_not_supported | intentional_deletion |
| S020 | external_repository_reference | human_not_supported | repository_boundary |
| S039 | confirmed_exists | human_not_supported | module_layout_resolution |
| S054 | confirmed_exists | human_not_supported | near_name_resolution |
| S066 | confirmed_missing_problematic | human_supported | unexplained_missing_prerequisite |

## Julgamentos individuais

### S039 — `confirmed_exists`

O caminho literal `types/storage.rs` não existe, mas o commit contém `crates/viewpoint-core/src/context/types/storage/mod.rs`. O arquivo tem exatamente 387 linhas e define `StorageState`, coincidindo com a descrição da tarefa. Trata-se de resolução de módulo Rust, não de implementação ausente. O humano e os dois LLMs foram excessivamente literais; a auditoria favorece `confirmed_exists` por caminho correspondente.

### S010 — `external_repository_reference`

A seção se chama Consumer Handoff e atribui explicitamente o follow-up ao `groundx-studio-harness`. O arquivo `xray_to_extract.py` não deveria estar em `groundx-python`. O humano confundiu a ausência local com defeito. O Luna-only identificou corretamente a fronteira de repositório.

### S066 — `confirmed_missing_problematic`

A tarefa descreve `offlineQueue.ts` como lógica existente, exige migração e preservação de comportamento e não marca o arquivo como novo. A árvore completa do commit não contém sequer o diretório de código `frontend/src`, nem há evidência de criação, remoção, mudança ou outro repositório. Este é o único dos seis casos em que o julgamento humano positivo permanece sustentado; ambos os pipelines também o classificaram corretamente.

### S015 — `expected_absence_move_or_delete`

O arquivo existia antes e registrava `JsonNullableJackson3Module`. O commit de implementação imediatamente anterior ao anchor removeu a configuração e a dependência. A tarefa também manda remover esse módulo. A ausência é consequência esperada da mudança. O humano ignorou a evidência longitudinal; a regra e o Luna-only acertaram.

### S054 — `confirmed_exists`

O literal usa `raw_http_test.go`, mas a árvore contém `pkg/forgejo/rawhttp_test.go`. O arquivo tem 287 linhas, importa `net/http/httptest` e define um helper baseado em `httptest.Server`, exatamente o padrão citado pela tarefa. O caso expõe uma falha do resolvedor de caminhos: ele procurou apenas o basename exato e não reconheceu a variante sem underscore.

### S020 — `external_repository_reference`

O anchor está no repositório `liverty-music/specification`, e a mensagem do commit afirma que a implementação ocorreu no repositório frontend, com referência a `liverty-music/frontend#253`. A ausência local de `src/entities/artist.ts` é esperada. O Luna-only acertou; o rótulo humano não é sustentado.

## Efeito interpretativo

- A concordância humana test-retest mostrou consistência, não validade. O mesmo viés literal foi repetido nas duas rodadas.
- O resultado original de 1 acerto em 6 positivos não deve mais ser interpretado diretamente como recall de 16,7%. Cinco dos seis denominadores eram falsos positivos humanos segundo a auditoria ampliada.
- Nos seis casos auditados, os dois pipelines reconheceram o único caso que permaneceu problemático, classificaram corretamente o estado de outros três e se abstiveram nos dois casos de resolução de caminho.
- Esse recorte não produz uma nova estimativa de recall: ele foi selecionado por rótulo humano positivo, auditado após observar as saídas dos modelos e contém apenas um positivo confirmado.

## Implicação para o pipeline

O próximo gargalo técnico não é apenas o prompt. A coleta deve resolver caminhos equivalentes antes do julgamento semântico, incluindo módulos `path.rs` versus `path/mod.rs`, pequenas variações de nome e referências explícitas a outros repositórios. Depois dessa correção, deve-se auditar uma amostra de negativos e abstenções. Sem isso, ainda não sabemos quantos positivos verdadeiros foram escondidos por erros humanos ou pelo próprio pipeline.
