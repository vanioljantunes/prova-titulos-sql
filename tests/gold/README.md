# Padrão-ouro

Transcrição HUMANA de uma prova completa, usada por `provas avaliar-gold` para
medir a qualidade da extração automática. **Não é gerado por modelo — preencha à
mão** a partir do PDF original.

## Como usar

1. Copie `template.json` para `<sigla>_<ano>.json` (ex.: `sbcm_2026.json`).
2. Transcreva TODAS as questões da prova (enunciado e alternativas literais).
3. Ingira a mesma prova com `provas ingest-prova` (+ gabarito, se houver).
4. Rode:

   ```
   provas avaliar-gold --prova-id N --gold tests/gold/sbcm_2026.json
   ```

O relatório sai por tipo de campo (categóricos / textuais / estruturais), com
acurácia exata, taxa de omissão e taxa de erro separadas.

## Formato

- `numero`: int, numeração canônica.
- `tipo`: multipla_escolha | discursiva | verdadeiro_falso.
- `status`: valida | anulada | gabarito_alterado (após gabarito definitivo).
- `gabarito_oficial`: letra, ou null se anulada/sem gabarito ingerido.
- `enunciado`: texto literal, sem alternativas.
- `alternativas`: lista completa `{letra, texto}` literais.
- `num_midias`: quantas mídias (ECG, figuras, tabelas) a questão exibe. Opcional;
  omita se não quiser avaliar mídia.
- Campos opcionais omitidos não pontuam contra a extração.
