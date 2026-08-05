"""Termos de uso e Política de Privacidade — páginas públicas.

Existem por três motivos concretos, não por formalidade:

1. A plataforma guarda credencial do Garmin Connect (cifrada) e token OAuth do
   Strava de terceiros. Isso precisa estar escrito.
2. Dados de treino, peso, frequência cardíaca e restrição alimentar são dado
   pessoal sensível de saúde (LGPD art. 5º, II) — tratamento exige base legal e
   finalidade declarada.
3. A IA prescreve treino e cardápio. Sem o aviso de que isso não substitui
   médico, nutricionista (CFN) nem educador físico (CREF), a responsabilidade
   por um problema de saúde do assinante fica com quem prescreveu.

A versão é gravada junto com o aceite no cadastro (`aceite_termos.versao`);
mudou o texto de forma relevante, sobe a versão para dar para saber quem
aceitou o quê.
"""
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()

VERSAO_TERMOS = "2026-08-05"

CONTROLADOR_NOME = "Marciano Luis Cadore"
CONTROLADOR_CIDADE = "Passo Fundo/RS"
CONTATO_WHATSAPP = "(54) 99944-1016"
CONTATO_EMAIL = "marcianocadore@hotmail.com"

_BASE = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{titulo} — MTB Nutrition</title>
  <style>
    :root {{ --green:#128c7e; --bg:#f7f9f8; --card:#fff; --text:#1a1a2e; --muted:#6b7280; --border:#e5e7eb; }}
    * {{ box-sizing:border-box; margin:0; padding:0; }}
    body {{ font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; background:var(--bg); color:var(--text); line-height:1.65; }}
    header {{ background:var(--green); color:#fff; padding:26px 20px; }}
    header .wrap {{ max-width:760px; margin:0 auto; }}
    header a {{ color:#fff; opacity:.85; text-decoration:none; font-size:.85rem; }}
    header h1 {{ font-size:1.5rem; margin-top:8px; }}
    header .ver {{ font-size:.78rem; opacity:.8; margin-top:4px; }}
    main {{ max-width:760px; margin:0 auto; padding:28px 20px 60px; }}
    section {{ background:var(--card); border:1px solid var(--border); border-radius:12px; padding:20px 22px; margin-bottom:16px; }}
    h2 {{ font-size:1.05rem; color:var(--green); margin-bottom:10px; }}
    h3 {{ font-size:.92rem; margin:14px 0 6px; }}
    p, li {{ font-size:.92rem; color:#333; }}
    ul, ol {{ margin:8px 0 8px 20px; }}
    li {{ margin-bottom:5px; }}
    .destaque {{ background:#fff8e1; border-left:4px solid #f59e0b; padding:14px 16px; border-radius:8px; margin:14px 0; }}
    .destaque p {{ font-size:.9rem; }}
    footer {{ max-width:760px; margin:0 auto; padding:0 20px 50px; font-size:.82rem; color:var(--muted); text-align:center; }}
    footer a {{ color:var(--green); text-decoration:none; margin:0 8px; }}
    strong {{ color:var(--text); }}
  </style>
</head>
<body>
  <header><div class="wrap">
    <a href="/">← Voltar ao início</a>
    <h1>{titulo}</h1>
    <div class="ver">Versão {versao} · MTB Nutrition</div>
  </div></header>
  <main>{corpo}</main>
  <footer>
    <a href="/termos">Termos de uso</a>·<a href="/privacidade">Privacidade</a>·<a href="/">Início</a>
    <p style="margin-top:10px">{controlador} — {cidade}</p>
  </footer>
</body>
</html>"""


def _pagina(titulo: str, corpo: str) -> str:
    return _BASE.format(
        titulo=titulo, corpo=corpo, versao=VERSAO_TERMOS,
        controlador=CONTROLADOR_NOME, cidade=CONTROLADOR_CIDADE,
    )


_TERMOS = f"""
<section>
  <h2>1. O que é este serviço</h2>
  <p>O MTB Nutrition é uma plataforma que usa inteligência artificial para montar
  semanas de treino de ciclismo e musculação, enviá-las ao seu relógio ou ao seu
  rolo de treino, analisar as sessões executadas e sugerir cardápios ajustados ao
  treino do dia. O serviço é prestado por <strong>{CONTROLADOR_NOME}</strong>,
  {CONTROLADOR_CIDADE}.</p>
</section>

<section>
  <h2>2. Aviso de saúde — leia antes de treinar</h2>
  <div class="destaque">
    <p><strong>Os treinos, cargas, zonas e cardápios exibidos na plataforma são
    gerados automaticamente por inteligência artificial a partir dos dados que
    você informa. Eles têm caráter informativo e educacional.</strong></p>
    <p style="margin-top:8px">Nada aqui constitui consulta, diagnóstico,
    prescrição médica, prescrição dietética ou prescrição de exercício físico.
    A plataforma <strong>não substitui</strong> o acompanhamento de médico,
    de nutricionista inscrito no CFN/CRN ou de profissional de educação física
    inscrito no CREF.</p>
    <p style="margin-top:8px">Antes de iniciar ou alterar qualquer programa de
    treinamento ou alimentação, procure avaliação profissional — especialmente
    se você tem doença cardiovascular, metabólica ou renal, hipertensão,
    diabetes, está grávida, em pós-operatório, é menor de 18 anos, ou usa
    medicação de uso contínuo.</p>
    <p style="margin-top:8px"><strong>Pare o exercício imediatamente</strong> e
    procure atendimento se sentir dor no peito, falta de ar desproporcional,
    tontura, desmaio ou arritmia. Você é responsável por avaliar se está apto a
    executar o que a plataforma sugere, e por interromper o que não fizer
    sentido para o seu corpo naquele dia.</p>
  </div>
  <p>Ao usar a plataforma você declara estar em condições de saúde compatíveis
  com a prática de exercício físico, e assume o risco inerente à atividade
  esportiva — inclusive ao ciclismo em via pública, cujas regras de trânsito e
  equipamentos de segurança são de sua inteira responsabilidade.</p>
</section>

<section>
  <h2>3. Limites da inteligência artificial</h2>
  <p>As sugestões são probabilísticas: a IA pode errar, pode não considerar uma
  condição sua que não foi informada, e pode produzir recomendações inadequadas
  ao seu caso. Sempre revise o treino e o cardápio antes de executar. Quanto
  mais precisos os dados que você informa (peso, altura, idade, FC máxima, FTP,
  restrições), melhor a saída — mas a revisão continua sendo sua.</p>
</section>

<section>
  <h2>4. Sua conta</h2>
  <ul>
    <li>Você é responsável por manter sua senha em sigilo e por tudo que
    acontecer na sua conta.</li>
    <li>A conta é pessoal e intransferível. Cada assinatura serve a um atleta.</li>
    <li>Informe dados verdadeiros. Dado errado gera treino e cardápio errados —
    e, no caso de peso e frequência cardíaca, isso tem consequência real.</li>
    <li>Só cadastre um número de WhatsApp que seja seu. Cadastrar número de
    terceiro para enviar mensagens é uso indevido e encerra a conta.</li>
  </ul>
</section>

<section>
  <h2>5. Teste grátis, assinatura e pagamento</h2>
  <ul>
    <li>Todo novo cadastro recebe <strong>14 dias de teste grátis</strong>, com
    acesso completo, sem cartão e sem cobrança automática.</li>
    <li>Após o teste, o acesso completo custa <strong>R$ 24,99</strong> e é
    liberado por <strong>30 dias</strong> a cada pagamento.</li>
    <li>O pagamento é feito por <strong>Pix</strong>. Você envia o comprovante
    pelo WhatsApp {CONTATO_WHATSAPP} e o acesso é liberado após a conferência,
    normalmente no mesmo dia útil.</li>
    <li><strong>Não há cobrança recorrente nem renovação automática.</strong>
    Nenhum dado de cartão é solicitado ou armazenado. Se você não pagar de novo,
    o acesso simplesmente vence — não existe dívida nem cobrança posterior.</li>
    <li>Pagando antes do vencimento, os dias restantes são somados ao novo
    período: você não perde o que já pagou.</li>
    <li>Vencido o acesso, seus dados <strong>não são apagados</strong>. Você
    continua conseguindo consultar o histórico do que já treinou, e recupera o
    acesso completo ao renovar.</li>
  </ul>
  <h3>Cancelamento e reembolso</h3>
  <p>Para cancelar, basta não pagar o próximo período. Se você desistir em até
  <strong>7 dias</strong> após um pagamento, devolvemos o valor integral por Pix
  mediante pedido pelo WhatsApp — é o direito de arrependimento do art. 49 do
  Código de Defesa do Consumidor, aplicado a contratações fora de
  estabelecimento comercial.</p>
</section>

<section>
  <h2>6. Integrações com Garmin, Strava e WhatsApp</h2>
  <p>A conexão com essas plataformas é opcional e feita por você. Ao conectar,
  você autoriza a leitura das suas atividades e o envio de treinos planejados
  para a sua conta. Você pode desconectar a qualquer momento pela tela de
  integração — o que revoga o acesso e apaga as credenciais guardadas.</p>
  <p>Garmin, Strava, Zwift, MyWhoosh e Twilio são serviços de terceiros, sem
  vínculo com esta plataforma. Mudanças, instabilidades ou bloqueios feitos por
  eles podem interromper a integração sem que isso configure descumprimento
  deste contrato.</p>
</section>

<section>
  <h2>7. Disponibilidade</h2>
  <p>O serviço é oferecido "como está". Buscamos manter tudo no ar, mas não há
  garantia de disponibilidade ininterrupta: manutenção, falha de terceiros ou
  indisponibilidade dos provedores de IA podem gerar interrupções. Interrupção
  prolongada e comprovada gera compensação em dias de acesso.</p>
</section>

<section>
  <h2>8. Limitação de responsabilidade</h2>
  <p>Na máxima extensão permitida pela lei brasileira, a responsabilidade por
  qualquer perda ligada ao uso da plataforma fica limitada ao valor pago por
  você nos 12 meses anteriores ao fato. Isto não afasta a responsabilidade por
  dolo, por culpa grave, nem os direitos que o Código de Defesa do Consumidor
  garante a você e que não podem ser renunciados.</p>
</section>

<section>
  <h2>9. Encerramento</h2>
  <p>Podemos encerrar contas que descumpram estes termos (compartilhamento de
  acesso, uso de número de terceiro, tentativa de burlar limites, uso que
  prejudique outros assinantes). Havendo período pago não usufruído, ele é
  devolvido proporcionalmente.</p>
</section>

<section>
  <h2>10. Alterações e foro</h2>
  <p>Mudanças relevantes nestes termos são comunicadas pelo WhatsApp e pela
  própria plataforma com antecedência razoável. Aplica-se a lei brasileira; fica
  eleito o foro do domicílio do consumidor.</p>
  <h3>Contato</h3>
  <p>WhatsApp {CONTATO_WHATSAPP} · {CONTATO_EMAIL}</p>
</section>
"""

_PRIVACIDADE = f"""
<section>
  <h2>1. Quem trata seus dados</h2>
  <p>O controlador dos dados é <strong>{CONTROLADOR_NOME}</strong>,
  {CONTROLADOR_CIDADE}, contato {CONTATO_WHATSAPP} · {CONTATO_EMAIL}. Este
  documento segue a Lei Geral de Proteção de Dados (Lei 13.709/2018).</p>
</section>

<section>
  <h2>2. Que dados coletamos</h2>
  <h3>Cadastro</h3>
  <ul>
    <li>Nome, login, senha (guardada apenas como hash bcrypt — ninguém, nem nós,
    consegue lê-la) e número de WhatsApp.</li>
  </ul>
  <h3>Dados de saúde e desempenho <span style="color:#c62828">(dado sensível)</span></h3>
  <ul>
    <li>Idade, sexo, peso, altura, frequência cardíaca máxima e de limiar, zonas
    de FC e de potência, FTP.</li>
    <li>Atividades executadas: duração, distância, altimetria, frequência
    cardíaca, potência, cadência, calorias e o arquivo <code>.fit</code> da
    sessão.</li>
    <li>Cargas levantadas na academia e sua percepção sobre cada sessão.</li>
    <li>Objetivo (performance, emagrecimento, prova) e preferências alimentares.</li>
  </ul>
  <h3>Credenciais de integração</h3>
  <ul>
    <li>Credenciais do Garmin Connect, <strong>cifradas</strong> com chave
    Fernet antes de gravar. Nunca ficam em texto puro no banco nem em log.</li>
    <li>Tokens OAuth do Strava (acesso somente leitura de atividades).</li>
  </ul>
  <h3>Conversas</h3>
  <ul>
    <li>Mensagens trocadas com o assistente de IA no portal e no WhatsApp.</li>
  </ul>
</section>

<section>
  <h2>3. Por que tratamos (finalidade e base legal)</h2>
  <ul>
    <li><strong>Execução do contrato</strong> (art. 7º, V): gerar sua semana de
    treino, calcular carga, analisar sessões, montar cardápios e enviar treinos
    ao seu dispositivo. Sem esses dados, o serviço simplesmente não funciona.</li>
    <li><strong>Consentimento</strong> (art. 11, I) para os dados de saúde:
    dado no cadastro e revogável a qualquer momento — revogar implica encerrar
    a conta, porque o serviço não existe sem eles.</li>
    <li><strong>Legítimo interesse</strong> (art. 7º, IX): segurança da conta,
    prevenção a fraude e melhoria do produto a partir de dados agregados.</li>
    <li><strong>Obrigação legal</strong> (art. 7º, II): registros de acesso
    exigidos pelo Marco Civil da Internet.</li>
  </ul>
</section>

<section>
  <h2>4. Com quem compartilhamos</h2>
  <p>Não vendemos seus dados. Não cedemos a anunciante. O compartilhamento é
  apenas o necessário para o serviço funcionar:</p>
  <ul>
    <li><strong>Provedores de IA</strong> (Anthropic e Google) — recebem o
    contexto do seu treino para gerar plano e análise. Não recebem seu nome,
    telefone, login nem senha. Os provedores não usam esse conteúdo para treinar
    modelos.</li>
    <li><strong>Garmin / Strava</strong> — apenas se você conectar, e apenas
    para ler suas atividades e enviar treinos planejados.</li>
    <li><strong>Twilio</strong> — para entregar as mensagens de WhatsApp.</li>
    <li><strong>Amazon Web Services e MongoDB Atlas</strong> — hospedagem e
    banco de dados.</li>
    <li><strong>Autoridades</strong>, quando houver ordem judicial.</li>
  </ul>
  <p>Alguns desses provedores processam dados fora do Brasil. A transferência
  internacional se apoia no art. 33 da LGPD e nas cláusulas contratuais dos
  próprios fornecedores.</p>
</section>

<section>
  <h2>5. Por quanto tempo guardamos</h2>
  <ul>
    <li>Dados de conta e treino: enquanto sua conta existir.</li>
    <li>Após pedido de exclusão: apagados em até <strong>30 dias</strong>,
    exceto o mínimo exigido por lei (registros de acesso, guardados por 6 meses
    conforme o Marco Civil).</li>
    <li>Credenciais de integração: apagadas assim que você desconecta.</li>
  </ul>
</section>

<section>
  <h2>6. Segurança</h2>
  <ul>
    <li>Senhas guardadas como hash bcrypt, nunca em texto puro.</li>
    <li>Credenciais do Garmin cifradas com Fernet (AES-128 em modo CBC + HMAC).</li>
    <li>Sessões autenticadas por cookie HttpOnly assinado com HMAC-SHA256 e
    expiração por inatividade.</li>
    <li>Acesso ao banco restrito à aplicação.</li>
  </ul>
  <p>Nenhum sistema é imune. Em caso de incidente com risco relevante, avisamos
  você e a ANPD, como manda o art. 48 da LGPD.</p>
</section>

<section>
  <h2>7. Seus direitos</h2>
  <p>A LGPD (art. 18) garante a você: confirmação de que tratamos seus dados;
  acesso a eles; correção do que estiver incompleto ou errado; anonimização ou
  eliminação de dados desnecessários; portabilidade; informação sobre com quem
  compartilhamos; e revogação do consentimento.</p>
  <p>Para exercer qualquer um deles, é só chamar no WhatsApp
  {CONTATO_WHATSAPP} ou escrever para {CONTATO_EMAIL}. Respondemos em até 15
  dias.</p>
</section>

<section>
  <h2>8. Menores de idade</h2>
  <p>A plataforma não se destina a menores de 18 anos. Não coletamos
  intencionalmente dados de menores; identificado o caso, a conta é encerrada e
  os dados apagados.</p>
</section>

<section>
  <h2>9. Cookies</h2>
  <p>Usamos apenas um cookie, o de sessão (<code>mtb_auth</code>), estritamente
  necessário para manter você logado. Não há cookie de publicidade, de rastreio
  ou de terceiros.</p>
</section>
"""


@router.get("/termos", response_class=HTMLResponse, include_in_schema=False)
async def termos():
    return HTMLResponse(_pagina("Termos de Uso", _TERMOS))


@router.get("/privacidade", response_class=HTMLResponse, include_in_schema=False)
async def privacidade():
    return HTMLResponse(_pagina("Política de Privacidade", _PRIVACIDADE))
