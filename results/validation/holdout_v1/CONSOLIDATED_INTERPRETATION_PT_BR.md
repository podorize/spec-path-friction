# Interpretação consolidada: repetição humana e comparação com GPT-6 Luna

## 1. Pergunta avaliada

Esta etapa investigou se referências OpenSpec com `exists_at_anchor = 0` podem ser classificadas semanticamente de modo confiável por:

1. um pipeline híbrido, no qual regras determinísticas resolvem parte dos casos e o GPT-6 Luna recebe apenas os casos encaminhados; ou
2. GPT-6 Luna em todos os 90 casos.

O mesmo avaliador humano classificou os 90 casos em duas rodadas. A repetição não cria um padrão-ouro independente: ela mede a estabilidade do próprio julgamento humano.

## 2. Estabilidade da referência humana

- Concordância exata entre as oito classes: 56,7% (51/90).
- Concordância entre os três estados `problematic`, `nonproblematic` e `unknown`: 63,3% (57/90).
- Kappa de Cohen em três estados: 0,422.
- Casos decisivos e estáveis nas duas rodadas: 42.
- Casos problemáticos estáveis: 6.
- Casos não problemáticos estáveis: 36.
- Casos desconhecidos estáveis: 15.
- Casos que mudaram de estado: 33.

Onze registros da segunda rodada mencionaram falha temporária de acesso ao GitHub. Excluindo-os apenas como análise de sensibilidade, a concordância em três estados sobe para 67,1%. Portanto, indisponibilidade explica parte, mas não toda, a instabilidade.

## 3. Comparação primária nos 42 casos decisivos estáveis

| Métrica | Determinístico + Luna | Luna em todos os casos |
| --- | ---: | ---: |
| Cobertura | 64,3% | 90,5% |
| Precisão positiva | 100,0% | 100,0% |
| Sensibilidade fim a fim | 16,7% | 16,7% |
| Especificidade fim a fim | 63,9% | 94,4% |
| F1 fim a fim | 28,6% | 28,6% |
| Acurácia fim a fim | 57,1% | 83,3% |
| Acurácia entre casos classificados | 88,9% | 92,1% |

As duas arquiteturas encontraram apenas 1 dos 6 positivos estáveis. Em cada uma, a precisão de 100% corresponde a 1 verdadeiro positivo e 0 falsos positivos. Seu intervalo de Wilson de 95% é 20,7% a 100%, evidenciando que a estimativa é extremamente frágil. A sensibilidade de 16,7% tem intervalo de 3,0% a 56,4%.

O Luna-only foi 26,2 pontos percentuais mais acurado do que o híbrido nesta amostra pareada; o intervalo bootstrap de 95% para a diferença híbrido menos Luna foi de -42,9 a -9,5 pontos. O teste exato de McNemar produziu `p = 0,0074`. Essa vantagem ocorreu na classificação de casos não problemáticos e na redução de abstenções, não na detecção de positivos: a diferença de sensibilidade foi zero.

## 4. Onde o híbrido falhou

Nos 42 casos estáveis:

- As regras determinísticas classificaram 23 casos. Acertaram 20 negativos, mas classificaram como não problemáticos todos os 3 positivos estáveis que receberam.
- As regras se abstiveram em 11 casos, todos negativos segundo a referência estável. Essas abstenções foram seguras, porém reduziram a cobertura.
- O estágio semântico do Luna recebeu 8 casos. Classificou 4 corretamente e se absteve em 4; entre os classificados estava o único positivo detectado.

Assim, o problema do híbrido não é apenas incerteza do LLM. Regras de ciclo de vida interceptaram metade dos positivos estáveis antes da análise semântica e os converteram em falsos negativos.

## 5. Resultado semântico mais amplo

Nos 51 casos em que o humano repetiu exatamente a mesma classe:

- acurácia exata do híbrido: 43,1%;
- acurácia exata do Luna-only: 78,4%;
- macro-F1 do híbrido: 43,4%;
- macro-F1 do Luna-only: 75,3%.

Nos 57 casos estáveis em três estados, a acurácia foi 54,4% para o híbrido e 80,7% para o Luna-only. Isso sustenta o uso do Luna como instrumento de triagem e anotação semântica, mas não demonstra capacidade suficiente para identificar automaticamente todos os casos problemáticos.

## 6. Custo observado

- Híbrido: 18 chamadas ao Luna; custo estimado de tokens de US$ 0,0323.
- Luna-only: 92 tentativas para 90 respostas finais; custo estimado de US$ 0,1092.

O híbrido economizou aproximadamente US$ 0,077 nesta amostra, mas perdeu cobertura e cerca de 26 pontos de acurácia. Dado o baixo custo absoluto do Luna, essa economia não compensou a perda de desempenho.

## 7. Conclusão científica

O desenho híbrido congelado deve ser rejeitado em sua forma atual. O Luna-only é claramente superior para cobertura, concordância semântica e classificação de casos não problemáticos. Entretanto, nenhuma das duas arquiteturas mostrou sensibilidade adequada para funcionar como detector definitivo de referências problemáticas.

O resultado mais defensável não é “o LLM classifica corretamente referências ausentes”. É:

> A ausência literal de um caminho no commit requer interpretação semântica; regras determinísticas de ciclo de vida podem introduzir falsos negativos, enquanto um LLM barato amplia substancialmente a cobertura e a concordância semântica. Contudo, a instabilidade da avaliação humana e a baixa sensibilidade nos poucos positivos estáveis impedem seu uso autônomo como classificador definitivo.

## 8. Próximo passo recomendado

Antes de extrapolar para todos os registros com `exists_at_anchor = 0`, deve-se realizar uma auditoria qualitativa focalizada nos seis positivos humanos estáveis. Essa auditoria deve verificar, sem alterar retrospectivamente a avaliação primária:

1. qual evidência levou o humano a considerar cada caso problemático;
2. por que as regras chamaram três deles de movimento/remoção esperada;
3. por que o Luna se absteve em dois e classificou dois como não problemáticos;
4. se o prompt ou o pacote de evidências omitiu sinais essenciais;
5. se existe uma regra conservadora para encaminhar esses casos à revisão humana sem criar muitos falsos positivos.

Após essa auditoria, a decisão metodológica deve ser entre: (a) usar Luna-only como triagem com revisão humana dos candidatos e das abstenções; ou (b) reformular a pergunta do paper para estudar a incerteza e a fricção de rastreabilidade, em vez de prometer classificação automática dos casos problemáticos.
