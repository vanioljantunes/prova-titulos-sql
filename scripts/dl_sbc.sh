#!/bin/bash
# Download SBC TEC exams/gabaritos/editais 2013-2026
OUT="/c/Users/vanio/AppData/Local/Temp/claude/C--Users-vanio/0fd34411-41fc-46c3-ab62-045aaa8b90df/scratchpad/provas-titulo/SBC-TEC"
mkdir -p "$OUT"
S3="https://s3.sa-east-1.amazonaws.com/the-hive-cms.production/a0ccb5e4-7703-4d9b-8275-9d636cf6f5c7"

dl() { # dl <url> <outfile>
  local f="$OUT/$2"
  if [ -s "$f" ]; then echo "SKIP $2"; return; fi
  curl -sL --fail "$1" > "$f" && echo "OK   $2 ($(stat -c%s "$f") bytes)" || echo "FAIL $2"
}

gd() { # gd <fileid> <outfile>
  local f="$OUT/$2"
  if [ -s "$f" ]; then echo "SKIP $2"; return; fi
  curl -sL --fail "https://drive.google.com/uc?export=download&id=$1" > "$f" && echo "OK   $2 ($(stat -c%s "$f") bytes)" || echo "FAIL $2"
}

# 2026
gd 1QyobppZ9yiCWGD6duEIYbGTGr0GbQrMF "2026_edital.pdf"
gd 1TOS7wm_AjikS0aDZIJAWySjUHolb-K_9 "2026_errata_edital.pdf"

# 2025
gd 1-YiLzAtFSjZlSq97Vh1GjZjgLolEnv7H "2025_edital.pdf"
gd 1tR3WZamnyli_R3djQaWMYpAGV11Cqbbq "2025_errata_edital.pdf"
dl "https://cdn.prod.website-files.com/687e81b06b7964d7f9fb44f5/6938742218ab46ae7d73af74_GABARITO%20-%20PROVA%20TE%C3%93RICA.pdf" "2025_gabarito_prova1_teorica.pdf"
dl "https://cdn.prod.website-files.com/687e81b06b7964d7f9fb44f5/69387440d19b8dec629a24da_GABARITO%20-%20PROVA%20TE%C3%93RICA-PR%C3%81TICA.pdf" "2025_gabarito_prova2_teorico-pratica.pdf"
gd 1Fcbbvun4vKaPZ9dA8pZuV-yIXtt8m8f1 "2025_gabarito_prova1_pos-recursos.pdf"
gd 1s9Pj4A6ru7wJUCQnuY6vWdu6CpAKR5V- "2025_gabarito_prova2_pos-recursos.pdf"

# 2024
dl "$S3/19b8db00-226c-4102-8146-4bf6e62b1c07" "2024_edital.pdf"
dl "$S3/d6a08266-51fc-4f4e-ba8c-ab360bbb3c0b" "2024_errata_edital.pdf"
dl "$S3/cfc234d8-fe6b-49d0-8d91-83646ecfc5d3" "2024_gabarito_prova1_teorica.pdf"
dl "$S3/21b63ea6-e940-4d01-80fc-83e016f727fa" "2024_gabarito_prova2_teorico-pratica.pdf"
dl "$S3/45bd8938-63d3-41e8-bdb4-16d2d118c133" "2024_errata1_gabarito.pdf"
dl "$S3/f4f011ae-8ba4-4822-8f1f-cf4d013a0f43" "2024_errata2_gabarito.pdf"
dl "https://cdn.prod.website-files.com/687e81b06b7964d7f9fb44f5/6941a08012538ef41be2a3d4_gabarito-prova-teorico-pratica.pdf" "2024_gabarito_prova2_pos-recursos.pdf"

# 2023
dl "$S3/50e576d7-c535-4fc2-95ec-ac1c20026ff5" "2023_edital.pdf"
dl "https://www.cjtec.cardiol.br/_files/ugd/b16e09_f6881fba2b3f4524a86e9815c42ce45b.pdf" "2023_gabarito_prova1_teorica.pdf"
dl "https://www.cjtec.cardiol.br/_files/ugd/b16e09_d247b30f699f4540a8172a7f1104c296.pdf" "2023_gabarito_prova2_teorico-pratica.pdf"
dl "$S3/79e61ecd-469e-435e-bd26-c25eb65fced1" "2023_gabarito_prova1_pos-recursos.pdf"

# 2022
dl "$S3/cdd03b34-36bf-46d8-b509-d5a51d862e4b" "2022_edital.pdf"
dl "$S3/d1bce554-94a4-4d30-97fe-ba073699814e" "2022_errata_edital.pdf"
dl "$S3/4b880462-ca31-4370-badc-f0fcc3684648" "2022_gabarito_prova1_teorica.pdf"
dl "$S3/a6621fea-53c6-483f-9e63-1b56a2a573ca" "2022_gabarito_prova2_teorico-pratica.pdf"

# 2021
dl "$S3/62375bc3-3d50-4c0b-9eed-be4481b0071a" "2021_edital.pdf"
dl "$S3/4183372f-71a6-432d-b423-baf31254cdeb" "2021_errata1_edital.pdf"
dl "$S3/be925824-987a-43d0-bb80-ac85ae93273a" "2021_errata2_edital.pdf"
dl "$S3/a7bfd308-25f6-4f1f-b7ec-25b24faf54b2" "2021_gabarito_oficial.pdf"

# 2020
dl "$S3/17266569-40da-4ffc-a020-1283574b166e" "2020_edital.pdf"
dl "$S3/7424a439-f143-4619-b05c-cda4ff59a918" "2020_errata_edital.pdf"
dl "$S3/3c9f1c5f-05d4-41f5-9a86-29fd120f99cb" "2020_gabarito.pdf"
dl "$S3/3f1e479a-03e3-49e4-85fa-85e2700ab0d4" "2020_gabarito_pos-recursos.pdf"

# 2019
dl "$S3/34e18424-fa96-4efd-9ec0-db4c02166c70" "2019_edital.pdf"
dl "$S3/b6390815-283f-4d25-bc11-6fd5d5e3dc91" "2019_gabarito_provaA.pdf"
dl "$S3/751a8531-644b-43e3-99b0-6f8f6bddec87" "2019_gabarito_provaB.pdf"
dl "$S3/a0d17132-73a6-40bb-b3bf-0041fc3b5baa" "2019_gabarito_provaC.pdf"
dl "$S3/25fed06b-acdd-4a34-8238-922ab2402d7c" "2019_gabarito_provaD.pdf"
dl "$S3/d50e1ce2-c54b-4452-bee3-e2b0a8a02019" "2019_gabarito_provaA_pos-recursos.pdf"
dl "$S3/a812aae3-2318-4ab7-8768-97827d885d89" "2019_gabarito_provaB_pos-recursos.pdf"
dl "$S3/7c4aa9f1-e927-4119-996b-4fca3a7325fb" "2019_gabarito_provaC_pos-recursos.pdf"
dl "$S3/02f87e3e-a2d6-432b-86d3-8c430fbe157d" "2019_gabarito_provaD_pos-recursos.pdf"

# 2018
dl "$S3/c2c837be-1965-4bd0-9913-e0aecd524a6d" "2018_edital.pdf"
dl "$S3/ec10294c-6368-45de-abcf-d73ce7214d01" "2018_gabarito_pos-recursos.pdf"

# 2017
dl "$S3/521c4abb-8c75-4667-bc96-e04448d64963" "2017_edital.pdf"
dl "$S3/a1453caa-0842-43b6-99fc-46c0f25cd56a" "2017_gabarito_teorica_pos-recursos.pdf"
dl "$S3/8014a491-f053-40ec-9f1e-926db93900c8" "2017_edital_15anos-formado.pdf"

# 2016
dl "$S3/6fed4837-f362-404d-9ca9-61b8ca764ec5" "2016_edital.pdf"
dl "$S3/d3a3feea-9de6-453e-9dfd-3e3e93021086" "2016_gabarito_final_pos-recursos.pdf"

# 2015
dl "$S3/70918dd0-0615-4613-a55d-50b039493326" "2015_edital.pdf"
dl "$S3/5dd0d284-2112-47ac-b678-87aa0d20fd39" "2015_gabarito_final_pos-recursos.pdf"

# 2014
dl "$S3/e5c3d504-3e4f-4a29-9304-3f512057e05e" "2014_edital.pdf"
dl "$S3/1be632c5-0f31-4b97-bab8-916ee85da105" "2014_gabarito_oficial.pdf"

# 2013 (google drive)
gd 1tNrMBwSLdmKYqS5MBspnxMsM91n_bT4E "2013_edital.pdf"
gd 1Az19qN6FhPOhd2D2zD2oaaGPeYd3Txz4 "2013_gabarito_oficial.pdf"

echo "---- DONE ----"
ls -la "$OUT" | tail -60
