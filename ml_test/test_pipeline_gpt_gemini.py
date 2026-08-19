"""
Teste prático — pipeline GPT (escreve os prompts) + Gemini (gera as imagens)

Objetivo: em vez de usar os 8 prompts de cena fixos/genéricos direto, este
script primeiro manda pro GPT (OpenAI) o "esqueleto" de cada cena — nome +
todas as regras fixas já calibradas nos testes anteriores (não inventar
número, não sobrepor objetos, ortografia correta, não usar selo de
certificação falso, adaptar paleta à categoria etc.) — junto com o nome e a
descrição REAL do produto (ideal: já vindos da busca com Grounding, ver
test_gemini_grounding.py). O GPT devolve uma versão customizada de cada
prompt, específica pra esse produto. Só DEPOIS disso o Gemini gera as 8
imagens de verdade, usando os prompts que o GPT escreveu.

Isso é uma camada a mais (1 chamada de texto na OpenAI antes das 8 chamadas
de imagem no Gemini) — o objetivo é testar se prompts "escritos sob medida"
pra cada produto dão resultado melhor que os prompts fixos genéricos.

v11: array de cenas reordenado pra bater com a cartilha de 8 fotos (foto
principal 80%/fundo branco, problema que resolve, benefícios, como funciona,
detalhes premium, pessoa real usando, antes/depois, medidas reais) — ver
comentário acima do array ESQUELETOS_CENAS pra detalhe de cada uma. Reforçada
a regra de que o texto central de cada cena precisa estar ESCRITO na imagem,
não só sugerido visualmente.

Como rodar:
    pip install openai google-genai pillow
    export OPENAI_API_KEY="sua-key-openai"
    export GEMINI_API_KEY="sua-key-gemini"
    python test_pipeline_gpt_gemini.py foto.jpg categoria "nome do produto" "descrição do produto"

O 4º argumento (descrição) é opcional, mas recomendado — pode ser a
descrição que o script test_gemini_grounding.py já gerou pra esse produto,
colada aqui entre aspas.

IMPORTANTE — pontos não confirmados/observações:
1. Resolução: pedimos image_size="2K" (~2048x2048) no Gemini — isso já
   SUPERA a recomendação do Mercado Livre (mínimo recomendado 1200x1200),
   não existe um preset nativo de "exatamente 1200x1200" nesses modelos.
   Deixei um passo OPCIONAL de redimensionamento pra 1200x1200 comentado
   mais abaixo (função `redimensionar_para_1200`) — descomente a chamada
   dela no loop principal se quiser ativar. Por padrão fica desligado,
   porque gerar maior que o mínimo recomendado já atende o requisito.
2. Nome do modelo de texto da OpenAI usado abaixo (`MODEL_TEXTO`): não
   confirmei qual é o modelo de texto "padrão" mais atual disponível na
   sua conta em agosto de 2026 — se der erro de "model not found", troque
   pelo nome de um modelo de texto válido que aparecer no seu painel
   (platform.openai.com/docs/models).
3. O GPT é instruído a manter TODAS as regras fixas do esqueleto original
   (nada de inventar número/certificação/etc) — mas é uma instrução, não
   uma garantia. Confira o resultado gerado antes de confiar cegamente.
"""

import json
import mimetypes
import os
import sys
from pathlib import Path

from google import genai as google_genai
from google.genai import types as google_types
from openai import OpenAI

MODEL_TEXTO_OPENAI = "gpt-4.1"
MODEL_IMAGEM_GEMINI = "gemini-3.1-flash-image"

# v11: reordenado pra bater com a cartilha de 8 fotos definida pelo Henrique
# (baseada em feedback real de usuário: os dados principais precisam estar
# ESCRITOS na própria imagem, não só na legenda de texto separada — a
# legenda sozinha está rendendo menos do que o texto embutido na imagem).
# Por isso, a partir daqui, toda cena (exceto a #1, que é a capa limpa)
# carrega uma instrução explícita pra ter texto on-image com o dado central
# daquela cena — nunca só "sugerir visualmente".
ESQUELETOS_CENAS = [
    {
        "nome": "1-foto-principal",
        "regras_fixas": (
            "Foto principal/capa do anúncio. Produto ocupando OBRIGATORIAMENTE cerca de 80% "
            "da área da imagem, fundo branco puro (#FFFFFF), still de estúdio, luz suave e "
            "uniforme, sem sombra dura, altíssima fidelidade aos detalhes reais do produto "
            "(cor, forma, textura, rótulo). SEM texto sobreposto, SEM elemento gráfico extra "
            "— é a foto 'limpa' de catálogo. Não adicionar acessório, marca ou função "
            "inexistente. Quadrado 1:1."
        ),
        "is_cover": True,
    },
    {
        "nome": "2-problema-que-resolve",
        "regras_fixas": (
            "Cena publicitária quadrada que comunica visualmente O PROBLEMA/A DOR que esse "
            "produto resolve (ex: dificuldade, esforço, incômodo do dia a dia relacionado à "
            "categoria do produto) — SEM o produto em cena, ou com o produto discretamente à "
            "margem. Incluir um texto curto ON-IMAGE (título de 3-6 palavras) nomeando o "
            "problema, de forma honesta e baseada só no que é plausível pra essa categoria de "
            "produto (não inventar estatística, nem alegar um problema que o produto não "
            "resolve de fato). Tom visual de campanha, iluminação profissional. Texto em "
            "português correto, sem erro de ortografia. Quadrado 1:1."
        ),
    },
    {
        "nome": "3-beneficios-principais",
        "regras_fixas": (
            "Cartaz de benefícios quadrado, título grande de impacto no topo. Abaixo, 3-4 "
            "blocos com ícone line-icon + frase curta QUALITATIVA descrevendo um benefício "
            "real do produto (nunca número/medida/certificação inventada) — ESSE TEXTO "
            "PRECISA ESTAR ESCRITO NA IMAGEM, grande e legível, não só sugerido visualmente. "
            "Produto em destaque visual (grande, bem iluminado). Paleta coerente com a "
            "categoria. Texto em português correto. Quadrado 1:1."
        ),
    },
    {
        "nome": "4-como-funciona",
        "regras_fixas": (
            "Infográfico técnico premium quadrado, mostrando o produto sendo usado "
            "corretamente. EXATAMENTE 3 colunas verticais isoladas (sem nenhum elemento "
            "cruzando entre colunas), numeradas 01/02/03, cada uma com no máximo 1 mão "
            "humana interagindo com o produto. Título 'COMO FUNCIONA' sem acento, grande, "
            "ON-IMAGE. Uma palavra curta em caixa alta abaixo de cada coluna (sem acentuação, "
            "ortografia revisada). Mãos adultas realistas, sem deformação. Não inventar "
            "peças/funções. Texto em português correto. Quadrado 1:1."
        ),
    },
    {
        "nome": "5-detalhes-premium",
        "regras_fixas": (
            "Still de close-up/macro quadrado, mostrando com riqueza de detalhe o acabamento, "
            "material e textura REAIS do produto (zoom em uma parte específica visível na "
            "foto de referência — nunca inventar um detalhe que não está lá). 2-3 linhas de "
            "chamada finas apontando pra características visíveis, com rótulo curto e "
            "QUALITATIVO ESCRITO NA IMAGEM (ex: 'acabamento resistente', 'encaixe preciso') "
            "— nunca número/medida/certificação inventada. Iluminação de estúdio, fundo "
            "neutro. Texto em português correto. Quadrado 1:1."
        ),
    },
    {
        "nome": "6-pessoa-real-usando",
        "regras_fixas": (
            "Fotografia publicitária realista de uma pessoa real (adulta, anatomicamente "
            "correta, mãos sem deformação) usando o produto em sua função real, ambiente "
            "coerente com a categoria, luz natural, enquadramento fechado na interação "
            "pessoa-produto. Não inventar peça ou função. Sem texto sobreposto nesta cena "
            "(o objetivo aqui é transmitir confiança/realismo, não informação escrita). "
            "Quadrado 1:1."
        ),
    },
    {
        "nome": "7-comparacao-antes-depois",
        "regras_fixas": (
            "Imagem quadrada dividida em 2 metades lado a lado (SEM sobreposição entre as "
            "metades). Lado esquerdo: cenário representando a dificuldade/situação SEM o "
            "produto (rotulado 'ANTES' ou 'SEM', em português, ON-IMAGE, texto pequeno e "
            "discreto). Lado direito: mesma situação já resolvida COM o produto em uso "
            "(rotulado 'DEPOIS' ou 'COM'). NÃO alegar percentuais, tempo economizado ou "
            "qualquer resultado quantificado — é uma comparação qualitativa de situação, não "
            "uma alegação de performance mensurável. Linha divisória nítida entre os dois "
            "lados. Texto em português correto. Quadrado 1:1."
        ),
    },
    {
        "nome": "8-medidas-reais",
        "regras_fixas": (
            "Imagem quadrada de referência de tamanho do produto. SE E SOMENTE SE a descrição "
            "do produto fornecida abaixo contiver uma medida/dimensão real confirmada, "
            "mostrar um diagrama com linhas de medida e ESSE NÚMERO REAL escrito ON-IMAGE. "
            "SE NÃO houver medida real confirmada na descrição, NÃO INVENTAR NENHUM NÚMERO — "
            "em vez disso, gerar uma 'referência de escala visual': o produto posicionado ao "
            "lado de um objeto cotidiano comum e reconhecível (ex: uma mão humana, um celular, "
            "uma moeda — escolha o que for proporcionalmente coerente com o tamanho provável "
            "da categoria do produto), sem nenhum número impresso, só a comparação visual de "
            "tamanho. Fundo neutro, iluminação de estúdio. Texto em português correto (se "
            "houver). Quadrado 1:1."
        ),
    },
]


def carregar_imagem_gemini(caminho: str) -> google_types.Part:
    mime, _ = mimetypes.guess_type(caminho)
    with open(caminho, "rb") as f:
        dados = f.read()
    return google_types.Part.from_bytes(data=dados, mime_type=mime or "image/jpeg")


def gerar_prompts_customizados(client_openai, nome_produto, descricao_produto):
    """Manda o esqueleto das 8 cenas + dados do produto pro GPT, pede de volta
    um prompt customizado por cena, em JSON."""

    esqueletos_texto = "\n\n".join(
        f'CENA "{c["nome"]}": {c["regras_fixas"]}' for c in ESQUELETOS_CENAS
    )

    instrucao = f"""
Você escreve prompts de geração de imagem para o modelo Gemini (Google), para
anúncios de e-commerce no Mercado Livre.

Produto: {nome_produto}
Descrição real do produto (use como base factual, não invente além disso —
inclua aqui qualquer medida/dimensão real que você souber, pra cena 8 poder
usá-la; se não souber nenhuma medida real, não invente):
{descricao_produto or "(nenhuma descrição fornecida — baseie-se só no nome do produto)"}

Abaixo estão 8 "esqueletos" de cena, na ORDEM EXATA em que devem aparecer no
anúncio, cada um com REGRAS FIXAS já calibradas em testes anteriores para
evitar bugs visuais conhecidos (objetos se fundindo, texto com erro de
ortografia, dados numéricos inventados, selos de certificação falsos). Sua
tarefa: para cada cena, escrever um prompt final em português, específico
para ESTE produto (usando a descrição real acima), MANTENDO INTEGRALMENTE
todas as regras fixas listadas — você pode adicionar detalhes específicos do
produto, mas NUNCA remover ou enfraquecer uma regra fixa, e NUNCA inventar
número/medida/certificação que não esteja na descrição fornecida.

REGRA GERAL IMPORTANTE (vale pra todas as cenas que pedem texto on-image):
o texto/dado central de cada cena precisa aparecer ESCRITO DE FORMA VISÍVEL
NA PRÓPRIA IMAGEM, não apenas sugerido visualmente — feedback real de uso
mostrou que o comprador absorve muito mais informação do texto embutido na
imagem do que da legenda separada.

{esqueletos_texto}

Responda em JSON, formato exato:
{{"cenas": [{{"nome": "...", "prompt_final": "..."}}, ...]}}
Uma entrada por cena, na mesma ordem, usando o mesmo "nome" de cada uma.
"""

    resposta = client_openai.chat.completions.create(
        model=MODEL_TEXTO_OPENAI,
        messages=[{"role": "user", "content": instrucao}],
        response_format={"type": "json_object"},
    )

    dados = json.loads(resposta.choices[0].message.content)
    prompts_por_nome = {c["nome"]: c["prompt_final"] for c in dados["cenas"]}
    return prompts_por_nome


def redimensionar_para_1200(caminho_imagem):
    """OPCIONAL — desligado por padrão (não é chamada em lugar nenhum abaixo).
    Só ative se quiser forçar exatamente 1200x1200 em vez de usar o 2K nativo
    (~2048x2048) que já supera a recomendação do Mercado Livre."""
    from PIL import Image

    img = Image.open(caminho_imagem)
    img = img.resize((1200, 1200), Image.LANCZOS)
    img.save(caminho_imagem)


def main():
    if len(sys.argv) < 3:
        print(
            'Uso: python test_pipeline_gpt_gemini.py <foto> <categoria> '
            '"nome do produto" ["descrição do produto"]'
        )
        sys.exit(1)

    caminho_foto = sys.argv[1]
    categoria = sys.argv[2]
    nome_produto = sys.argv[3] if len(sys.argv) > 3 else "produto"
    descricao_produto = sys.argv[4] if len(sys.argv) > 4 else None

    openai_key = os.environ.get("OPENAI_API_KEY")
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if not openai_key or not gemini_key:
        print("Defina OPENAI_API_KEY e GEMINI_API_KEY antes de rodar.")
        sys.exit(1)

    client_openai = OpenAI(api_key=openai_key)
    client_gemini = google_genai.Client(api_key=gemini_key)

    print(f"1/2 — Pedindo pro GPT escrever os 8 prompts customizados para: {nome_produto}...")
    try:
        prompts_por_nome = gerar_prompts_customizados(client_openai, nome_produto, descricao_produto)
    except Exception as e:
        print(f"ERRO ao gerar prompts com o GPT: {e}")
        sys.exit(1)
    print("   Prompts recebidos. Seguindo para a geração de imagem.\n")

    imagem_produto = carregar_imagem_gemini(caminho_foto)
    pasta_saida = Path(f"saidas_pipeline_{categoria}")
    pasta_saida.mkdir(exist_ok=True)

    total = len(ESQUELETOS_CENAS)
    for i, esqueleto in enumerate(ESQUELETOS_CENAS, start=1):
        nome = esqueleto["nome"]
        prompt_final = prompts_por_nome.get(nome)
        if not prompt_final:
            print(f"[{i}/{total}] AVISO: GPT não devolveu prompt para '{nome}', pulando.")
            continue

        prompt_completo = (
            f"Usando a imagem de referência do produto anexada, gere uma nova foto "
            f"do MESMO produto exato (preserve rigorosamente cor, formato, proporções, "
            f"rótulos e texturas reais do objeto — não invente detalhes que o produto não tem). "
            f"{prompt_final}"
        )

        print(f"[{i}/{total}] Gerando (Gemini): {nome}...")

        try:
            response = client_gemini.models.generate_content(
                model=MODEL_IMAGEM_GEMINI,
                contents=[prompt_completo, imagem_produto],
                config=google_types.GenerateContentConfig(
                    response_modalities=["IMAGE"],
                    image_config=google_types.ImageConfig(aspect_ratio="1:1", image_size="2K"),
                ),
            )
        except Exception as e:
            print(f"    ERRO na chamada do Gemini para '{nome}': {e}")
            continue

        candidato = response.candidates[0] if response.candidates else None
        content = getattr(candidato, "content", None) if candidato else None
        parts = getattr(content, "parts", None) if content else None
        if not parts:
            motivo = getattr(candidato, "finish_reason", None) if candidato else None
            print(f"    ATENÇÃO: geração bloqueada/vazia para '{nome}'. finish_reason={motivo}")
            continue

        for part in parts:
            if part.inline_data is not None:
                caminho_saida = pasta_saida / f"foto_{i:02d}_{nome}.png"
                with open(caminho_saida, "wb") as f:
                    f.write(part.inline_data.data)
                # Descomente a linha abaixo se quiser forçar 1200x1200 exato
                # em vez de manter o 2K nativo:
                # redimensionar_para_1200(caminho_saida)
                print(f"    salvo em {caminho_saida}")

    print(f"\nPronto. Confira as imagens em {pasta_saida}/")


if __name__ == "__main__":
    main()
