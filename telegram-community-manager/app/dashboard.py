from fastapi.responses import HTMLResponse

DASHBOARD_HTML = r"""<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Telegram Community Manager</title>
  <style>
    body{font-family:system-ui,-apple-system,sans-serif;margin:0;background:#0b1020;color:#eef2ff}
    main{max-width:920px;margin:auto;padding:20px}
    .card{background:#151c33;border:1px solid #2a3558;border-radius:16px;padding:16px;margin:12px 0}
    input,textarea,button{box-sizing:border-box;width:100%;padding:12px;border-radius:10px;border:1px solid #3a466c;background:#0e1530;color:#fff;margin:6px 0}
    textarea{min-height:150px}
    button{background:#3563ff;border:0;font-weight:700}
    button.secondary{background:#28324f}
    button.danger{background:#8f2d3d}
    .grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}
    pre{white-space:pre-wrap;word-break:break-word;background:#090e1d;padding:12px;border-radius:10px}
    .ok{color:#72e89b}.warn{color:#ffd166}
    @media(max-width:640px){.grid{grid-template-columns:1fr}}
  </style>
</head>
<body>
<main>
  <h1>Telegram Community Manager</h1>
  <p>Dashboard mobile. La clé admin reste dans cette session du navigateur uniquement.</p>

  <section class="card">
    <h2>Connexion admin</h2>
    <input id="apiKey" type="password" placeholder="ADMIN_API_KEY">
    <button onclick="saveKey()">Utiliser cette clé</button>
    <div id="authState" class="warn">Clé non chargée</div>
  </section>

  <section class="card">
    <h2>Créer une campagne</h2>
    <input id="name" placeholder="Nom de campagne">
    <input id="target" placeholder="@groupe_cible ou lien Telegram">
    <button onclick="createCampaign()">Créer</button>
  </section>

  <section class="card">
    <h2>Campagne</h2>
    <input id="campaignId" inputmode="numeric" placeholder="ID campagne">
    <div class="grid">
      <button class="secondary" onclick="loadCampaign()">Actualiser</button>
      <button class="secondary" onclick="preflight()">Préflight Telegram</button>
    </div>
    <textarea id="usernames" placeholder="@user1&#10;@user2&#10;@user3"></textarea>
    <button onclick="importUsernames()">Importer les usernames</button>
    <div class="grid">
      <button onclick="runDry()">Lancer dry-run</button>
      <button class="secondary" onclick="inviteLink()">Créer lien fallback</button>
    </div>
  </section>

  <section class="card">
    <h2>Mode réel</h2>
    <p class="warn">Impossible tant que DRY_RUN=true côté serveur. L’activation demande aussi la confirmation exacte.</p>
    <input id="confirmLive" placeholder="ENABLE_LIVE_INVITES">
    <button class="danger" onclick="activateLive()">Activer live</button>
    <button class="danger" onclick="runLive()">Lancer un batch live</button>
  </section>

  <section class="card">
    <h2>Résultat</h2>
    <pre id="out">Prêt.</pre>
  </section>
</main>
<script>
let apiKey=sessionStorage.getItem("admin_api_key")||"";
document.getElementById("apiKey").value=apiKey;
if(apiKey) document.getElementById("authState").textContent="Clé chargée pour cette session";

function saveKey(){
  apiKey=document.getElementById("apiKey").value.trim();
  sessionStorage.setItem("admin_api_key",apiKey);
  document.getElementById("authState").textContent=apiKey?"Clé chargée":"Clé vide";
}
function cid(){
  const v=document.getElementById("campaignId").value.trim();
  if(!v) throw new Error("ID campagne manquant");
  return v;
}
async function api(path, method="GET", body=null){
  if(!apiKey) saveKey();
  const opt={method,headers:{"Authorization":"Bearer "+apiKey}};
  if(body!==null){opt.headers["Content-Type"]="application/json";opt.body=JSON.stringify(body);}
  const r=await fetch(path,opt);
  let data; try{data=await r.json()}catch{data={detail:await r.text()}}
  document.getElementById("out").textContent=JSON.stringify(data,null,2);
  if(!r.ok) throw new Error(data.detail||("HTTP "+r.status));
  return data;
}
async function createCampaign(){
  const d=await api("/campaigns","POST",{name:document.getElementById("name").value,target_group:document.getElementById("target").value});
  document.getElementById("campaignId").value=d.id;
}
async function loadCampaign(){await api("/campaigns/"+cid())}
async function importUsernames(){
  const usernames=document.getElementById("usernames").value.split(/\r?\n/).map(x=>x.trim()).filter(Boolean);
  await api("/campaigns/"+cid()+"/import","POST",{usernames});
}
async function preflight(){await api("/campaigns/"+cid()+"/preflight","POST",{})}
async function runDry(){await api("/campaigns/"+cid()+"/run","POST",{live:false,limit:100})}
async function inviteLink(){await api("/campaigns/"+cid()+"/invite-link","POST",{})}
async function activateLive(){
  await api("/campaigns/"+cid()+"/activate-live","POST",{confirmation:document.getElementById("confirmLive").value});
}
async function runLive(){await api("/campaigns/"+cid()+"/run","POST",{live:true,limit:25})}
</script>
</body>
</html>"""


def dashboard_response() -> HTMLResponse:
    return HTMLResponse(DASHBOARD_HTML)
