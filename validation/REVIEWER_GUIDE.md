# Guia de revisão de referências em tarefas OpenSpec

## Objetivo

Classificar se cada referência extraída de uma lista de tarefas OpenSpec
denota um arquivo existente, uma ausência esperada ou uma referência que não
deve ser interpretada literalmente como um arquivo. Avalie sempre o estado do
repositório no commit indicado pela planilha.

## Procedimento por linha

1. Abra `artifact_url` e leia a tarefa no trecho próximo a `reference_excerpt`.
2. Abra `anchor_code_url`. Quando ela apontar para `resolved_path`, esse é o
   caminho que o resolvedor automático localizou; quando não houver
   `resolved_path`, ela corresponde ao texto literal em `code_path`.
3. Registre seu identificador em `reviewer_id`, uma categoria em
   `manual_classification` e uma justificativa factual, breve, em
   `evidence_note`.
4. Caso não consiga abrir ou verificar o estado no commit, descreva o motivo
   em `access_issue` e use `inaccessible_or_invalid`.

## Categorias

| Categoria | Quando usar |
| --- | --- |
| `confirmed_exists` | O arquivo referenciado existe no commit indicado. |
| `confirmed_missing_problematic` | A tarefa requer que o arquivo exista ou seja alterado naquele caminho, mas ele está ausente. |
| `expected_absence_create` | A tarefa pede explicitamente a criação de um novo arquivo; portanto, a ausência é esperada. |
| `expected_absence_move_or_delete` | O caminho é explicitamente movido, renomeado, substituído ou removido. |
| `non_file_reference` | O texto é biblioteca, conceito, placeholder, padrão de busca, exemplo de teste ou outro objeto que não é um arquivo único. |
| `ambiguous_reference` | O contexto não permite decidir com segurança. |
| `inaccessible_or_invalid` | O commit, o artefato ou a evidência necessária não está acessível. |

## Regras conservadoras

- Não classifique uma ausência como problemática apenas porque o link literal
  retorna erro.
- Para uma tarefa que diz criar, mover, renomear, remover ou substituir, dê
  precedência à ação declarada no texto da tarefa.
- Um nome sem diretório ou uma referência começando por `../` é ambígua, salvo
  se a tarefa indicar claramente a base do caminho.
- Se a evidência for insuficiente, prefira `ambiguous_reference` a uma
  inferência sobre a implementação.
