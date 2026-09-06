---
version: 1
---

# Extração de uma questão de prova

Você extrai UMA única questão de prova de título de especialista médico. Recebe:
(1) o texto parseado do trecho da questão, e (2) a(s) imagem(ns) da(s) página(s)
onde ela aparece. Devolve o schema `QuestaoExtraida`.

Regras:

1. Extraia SOMENTE a questão de número indicado. Ignore questões vizinhas
   visíveis na imagem da página.
2. `enunciado`: texto integral do comando da questão, SEM as alternativas e SEM
   o texto-base compartilhado. Transcrição fiel — não corrija, não resuma, não
   complete texto cortado (se cortado/ilegível, use motivo_ausencia "ilegivel").
3. `contexto_compartilhado`: preencher apenas quando existe texto-base/caso
   clínico explicitamente compartilhado com outras questões (ex.: "Considerando
   o caso acima, responda às questões 12 a 14"). Questão autônoma → valor null
   com motivo_ausencia "nao_aplicavel". Informe também `contexto_tipo`.
4. `alternativas`: todas as alternativas com letra e texto LITERAIS, na ordem
   impressa. Texto ilegível → texto null + motivo_ausencia. NUNCA marque qual é
   a correta — gabarito não faz parte desta tarefa.
5. `midias`: registre TODA mídia que a questão referencia ou exibe (ECG,
   radiografia, ecocardiograma, tabela, gráfico), com página e uma descrição
   curta. Use a IMAGEM da página para confirmar a existência da mídia — o texto
   parseado frequentemente a perde.
6. Todo campo textual não-nulo deve trazer `trecho_fonte` (primeiros ~120
   caracteres do trecho original) e `pagina`.
7. Não invente nada. Omissão explícita (null + motivo) é sempre preferível a
   texto plausível.
