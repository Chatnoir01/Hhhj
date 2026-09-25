from fastapi.responses import HTMLResponse

DASHBOARD_HTML = r"""<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
  <title>Telegram Community Manager</title>
  <style>
    :root{color-scheme:dark}
    *{box-sizing:border-box}
    body{font-family:system-ui,-apple-system,sans-serif;margin:0;background:#0b1020;color:#eef2ff}
    main{max-width:900px;margin:auto;padding:18px}
    h1{font-size:28px;margin:8px 0 4px} h2{font-size:19px}
    .muted{color:#aeb9d6}.ok{color:#72e89b}.warn{color:#ffd166}.bad{color:#ff8b9a}
    .card{background:#151c33;border:1px solid #2a3558;border-radius:16px;padding:16px;margin:12px 0}
    .hidden{display:none}
    input,textarea,button{width:100%;padding:13px;border-radius:11px;border:1px solid #3a466c;background:#0e1530;color:#fff;margin:6px 0;font-size:16px}
    textarea{min-height:150px;resize:vertical}
    button{background:#3563ff;border:0;font-weight:700;cursor:pointer}
    button.secondary{background:#28324f}
    button:disabled{opacity:.45}
    .busy{opacity:.65;pointer-events:none}
    .grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}
    .status{padding:10px;border-radius:10px;background:#0b1228;margin-top:8px}
    pre{white-space:pre-wrap;word-break:break-word;background:#090e1d;padding:12px;border-radius:10px;max-height:360px;overflow:auto}
    @media(max-width:640px){.grid{grid-template-columns:1fr}}
  </style>
</head>
<body>
<main>
  <h1>Telegram Community Manager</h1>
  <p class="muted">Tout le setup et la campagne depuis le navigateur.</p>

  <section id="setupCard" class="card hidden">
    <h2>1. Premier setup</h2>
    <p class="muted">Ces valeurs sont chiffrées côté serveur et ne sont pas écrites dans GitHub.</p>
    <input id="setupPassword" type="password" autocomplete="new-password" placeholder="Créer un mot de passe admin (12 caractères min.)">
    <input id="apiId" inputmode="numeric" placeholder="Telegram API ID">
    <input id="apiHash" type="password" autocomplete="off" placeholder="Telegram API Hash">
    <input id="phone" type="tel" autocomplete="tel" placeholder="Numéro Telegram, ex. +32...">
    <input id="botToken" type="password" autocomplete="off" placeholder="Bot token (optionnel)">
    <button onclick="initializeSetup()">Enregistrer et ouvrir le panel</button>
  </section>

  <section id="loginCard" class="card hidden">
    <h2>Connexion admin</h2>
    <input id="loginPassword" type="password" autocomplete="current-password" placeholder="Mot de passe admin">
    <button onclick="login()">Se connecter</button>
  </section>

  <div id="panel" class="hidden">
    <section class="card">
      <h2>Lien public GitHub</h2>
      <p class="muted">Le panel peut rendre lui-même le port 8000 public depuis ce Codespace.</p>
      <button onclick="publishGitHub()">Afficher / réactiver le lien public</button>
      <div id="publicUrl" class="status warn">Lien public pas encore activé</div>
    </section>

    <section class="card">
      <h2>2. Connexion Telegram</h2>
      <div id="tgStatus" class="status warn">Statut à vérifier</div>
      <button class="secondary" onclick="refreshTelegramStatus()">Vérifier la session</button>
      <button onclick="sendCode()">Envoyer le code Telegram</button>
      <input id="otp" inputmode="numeric" autocomplete="one-time-code" placeholder="Code Telegram reçu">
      <button onclick="verifyCode()">Valider le code</button>
      <input id="twofa" type="password" autocomplete="current-password" placeholder="Mot de passe 2FA si demandé">
      <button class="secondary" onclick="verify2FA()">Valider le 2FA</button>
    </section>

    <section class="card">
      <h2>3. Créer la campagne</h2>
      <input id="name" placeholder="Nom de campagne">
      <input id="target" placeholder="@groupe_cible ou lien Telegram">
      <button onclick="createCampaign()">Créer la campagne</button>
      <input id="campaignId" inputmode="numeric" placeholder="ID campagne">
      <div class="grid">
        <button class="secondary" onclick="loadCampaign()">Actualiser</button>
        <button class="secondary" onclick="listCampaigns()">Voir mes campagnes</button>
        <button class="secondary" onclick="preflight()">Préflight Telegram</button>
      </div>
    </section>

    <section class="card">
      <h2>4. Importer les abonnés</h2>
      <textarea id="usernames" placeholder="@user1&#10;@user2&#10;@user3"></textarea>
      <button onclick="importUsernames()">Importer la liste collée</button>
      <input id="memberFile" type="file" accept=".txt,.csv,.xlsx">
      <button class="secondary" onclick="uploadFile()">Importer TXT / CSV / XLSX</button>
    </section>

    <section class="card">
      <h2>5. Analyser la campagne</h2>
      <p class="muted">Le dry-run résout et classe les comptes sans envoyer d'invitation.</p>
      <button id="dryRunBtn" onclick="runDry()">Lancer un batch dry-run</button>
      <p class="muted">Chaque appui analyse le prochain lot de 100 comptes. Les comptes déjà classés ne sont plus retraités en dry-run.</p>
      <div id="dryStatus" class="status muted">Prêt — aucun batch lancé</div>
      <button class="secondary" onclick="inviteLink()">Créer le lien d'invitation fallback</button>
    </section>

    <section class="card">
      <h2>6. Message d'invitation</h2>
      <p class="muted">Message manuel à copier. Aucun DM massif n'est envoyé automatiquement.</p>
      <textarea id="inviteMessage">🐈‍⬛ CHAT NOIR UHQ 🐈‍⬛

⚠️ Notre ancien canal a sauté et plusieurs personnes utilisent notre nom.

🐈‍⬛ Mon seul @ personnel : @chatnoir_uhq

🔗 Nouveau groupe officiel : [LIEN TELEGRAM]

⚠️ Faites attention aux faux comptes.</textarea>
      <input id="inviteUrl" type="url" placeholder="Colle ici le lien Telegram officiel">
      <button onclick="prepareInviteMessage()">Préparer le message</button>
      <button class="secondary" onclick="copyInviteMessage()">Copier le message</button>
      <div id="messageStatus" class="status muted">Le lien remplacera [LIEN TELEGRAM].</div>
    </section>

    <section class="card">
      <h2>Session</h2>
      <button class="secondary" onclick="logout()">Se déconnecter</button>
    </section>
  </div>

  <section class="card">
    <h2>Résultat</h2>
    <pre id="out">Chargement…</pre>
  </section>
</main>

<script>
let token=sessionStorage.getItem("tcm_token")||"";

function show(id,value=true){document.getElementById(id).classList.toggle("hidden",!value)}
function output(data){document.getElementById("out").textContent=JSON.stringify(data,null,2)}
function setToken(value){
  token=value||"";
  if(token) sessionStorage.setItem("tcm_token",token);
  else sessionStorage.removeItem("tcm_token");
}

async function request(path,method="GET",body=null,auth=true){
  const headers={};
  if(auth && token) headers["Authorization"]="Bearer "+token;
  const opt={method,headers};
  if(body!==null){headers["Content-Type"]="application/json";opt.body=JSON.stringify(body)}
  const r=await fetch(path,opt);
  let data; try{data=await r.json()}catch{data={detail:await r.text()}}
  output(data);
  if(!r.ok) throw new Error(data.detail||("HTTP "+r.status));
  return data;
}

async function boot(){
  try{
    const s=await request("/setup/status","GET",null,false);
    if(!s.configured){
      show("setupCard",true); show("loginCard",false); show("panel",false);
      return;
    }
    if(token){
      try{
        await request("/config/status");
        show("panel",true); show("loginCard",false); show("setupCard",false);
        await refreshTelegramStatus();
        try{await publishGitHub()}catch(e){}
        return;
      }catch(e){setToken("")}
    }
    show("loginCard",true); show("setupCard",false); show("panel",false);
  }catch(e){output({error:String(e)})}
}

async function initializeSetup(){
  const body={
    admin_password:document.getElementById("setupPassword").value,
    telegram_api_id:Number(document.getElementById("apiId").value),
    telegram_api_hash:document.getElementById("apiHash").value,
    telegram_phone:document.getElementById("phone").value,
    telegram_bot_token:document.getElementById("botToken").value||null
  };
  const d=await request("/setup/initialize","POST",body,false);
  setToken(d.token);
  document.getElementById("setupPassword").value="";
  document.getElementById("apiHash").value="";
  document.getElementById("botToken").value="";
  show("setupCard",false); show("loginCard",false); show("panel",true);
  await refreshTelegramStatus();
  try{await publishGitHub()}catch(e){}
}

async function login(){
  const d=await request("/auth/login","POST",{admin_password:document.getElementById("loginPassword").value},false);
  setToken(d.token);
  document.getElementById("loginPassword").value="";
  show("loginCard",false); show("panel",true);
  await refreshTelegramStatus();
  try{await publishGitHub()}catch(e){}
}

async function logout(){
  try{await request("/auth/logout","POST",{})}catch(e){}
  setToken(""); show("panel",false); show("loginCard",true);
}

async function publishGitHub(){
  const el=document.getElementById("publicUrl");
  try{
    const d=await request("/github/publish","POST",{});
    if(d.url){
      el.textContent=d.url; el.className="status ok";
      el.onclick=()=>window.open(d.url,"_blank");
    }else{
      el.textContent="Port public activé"; el.className="status ok";
    }
    return d;
  }catch(e){
    try{
      const d=await request("/github/public-url");
      if(d.url){
        el.textContent=d.url; el.className="status ok";
        el.onclick=()=>window.open(d.url,"_blank");
        return d;
      }
    }catch(_){}
    el.textContent="Utilise le lien du port 8000 dans Codespaces";
    el.className="status warn";
    return null;
  }
}

async function refreshTelegramStatus(){
  const d=await request("/telegram/auth/status");
  const el=document.getElementById("tgStatus");
  el.textContent=d.authorized?"Telegram connecté":"Telegram non connecté";
  el.className="status "+(d.authorized?"ok":"warn");
}
async function sendCode(){await request("/telegram/auth/send-code","POST",{})}
async function verifyCode(){
  const d=await request("/telegram/auth/verify-code","POST",{code:document.getElementById("otp").value});
  document.getElementById("otp").value="";
  if(d.requires_2fa){
    document.getElementById("tgStatus").textContent="Code accepté — 2FA requis";
  }else if(d.authorized){await refreshTelegramStatus()}
}
async function verify2FA(){
  const d=await request("/telegram/auth/verify-2fa","POST",{password:document.getElementById("twofa").value});
  document.getElementById("twofa").value="";
  if(d.authorized) await refreshTelegramStatus();
}

function cid(){
  const v=document.getElementById("campaignId").value.trim();
  if(!v) throw new Error("ID campagne manquant");
  return v;
}
async function createCampaign(){
  const d=await request("/campaigns","POST",{
    name:document.getElementById("name").value,
    target_group:document.getElementById("target").value
  });
  document.getElementById("campaignId").value=d.id;
}
async function loadCampaign(){await request("/campaigns/"+cid())}
async function listCampaigns(){
  const d=await request("/campaigns");
  if(d.campaigns && d.campaigns.length){
    const current=document.getElementById("campaignId").value.trim();
    if(!current) document.getElementById("campaignId").value=d.campaigns[0].id;
  }
  return d;
}
async function preflight(){await request("/campaigns/"+cid()+"/preflight","POST",{})}
async function importUsernames(){
  const usernames=document.getElementById("usernames").value.split(/\r?\n/).map(x=>x.trim()).filter(Boolean);
  await request("/campaigns/"+cid()+"/import","POST",{usernames});
}
async function uploadFile(){
  const file=document.getElementById("memberFile").files[0];
  if(!file) throw new Error("Choisis un fichier");
  const form=new FormData(); form.append("file",file);
  const r=await fetch("/campaigns/"+cid()+"/import-file",{
    method:"POST",
    headers:{"Authorization":"Bearer "+token},
    body:form
  });
  let d; try{d=await r.json()}catch{d={detail:await r.text()}}
  output(d); if(!r.ok) throw new Error(d.detail||("HTTP "+r.status));
}
async function runDry(){
  const btn=document.getElementById("dryRunBtn");
  const status=document.getElementById("dryStatus");
  let campaignId;
  try{campaignId=cid()}catch(e){output({ok:false,error:e.message});status.textContent=e.message;status.className="status bad";return}
  btn.disabled=true; btn.classList.add("busy");
  status.textContent="Dry-run lancé côté serveur…"; status.className="status warn";
  try{
    const started=await request("/campaigns/"+campaignId+"/run-async","POST",{live:false,limit:100});
    const jobId=started.job_id;
    let failures=0;
    for(let attempt=0;attempt<180;attempt++){
      await new Promise(resolve=>setTimeout(resolve,2000));
      try{
        const job=await request("/campaign-runs/"+jobId);
        failures=0;
        if(job.status==="completed"){
          status.textContent="Dry-run terminé"; status.className="status ok";
          output({action:"dry_run",job_id:jobId,...job.result});
          return;
        }
        if(job.status==="failed"){
          throw new Error(job.error||"Traitement serveur échoué");
        }
        status.textContent="Dry-run en cours côté serveur…"; status.className="status warn";
      }catch(e){
        failures++;
        if(failures<5){
          status.textContent="Connexion momentanément perdue — le serveur continue…";
          status.className="status warn";
          continue;
        }
        throw e;
      }
    }
    throw new Error("Le traitement continue mais le suivi a expiré. Actualise la campagne.");
  }catch(e){
    status.textContent="Suivi interrompu : "+e.message; status.className="status bad";
    output({ok:false,action:"dry_run",error:e.message});
  }finally{
    btn.disabled=false; btn.classList.remove("busy");
  }
}
async function inviteLink(){
  const d=await request("/campaigns/"+cid()+"/invite-link","POST",{});
  const link=d.link||d.invite_link||d.url;
  if(link){
    document.getElementById("inviteUrl").value=link;
    prepareInviteMessage();
  }
  return d;
}
function prepareInviteMessage(){
  const box=document.getElementById("inviteMessage");
  const link=document.getElementById("inviteUrl").value.trim();
  if(!link){
    document.getElementById("messageStatus").textContent="Ajoute d'abord le lien Telegram officiel.";
    document.getElementById("messageStatus").className="status warn";
    return box.value;
  }
  box.value=box.value.replace(/\[LIEN TELEGRAM\]/g,link);
  document.getElementById("messageStatus").textContent="Message prêt à copier.";
  document.getElementById("messageStatus").className="status ok";
  return box.value;
}
async function copyInviteMessage(){
  const text=prepareInviteMessage();
  try{
    await navigator.clipboard.writeText(text);
    document.getElementById("messageStatus").textContent="Message copié.";
    document.getElementById("messageStatus").className="status ok";
  }catch(e){
    document.getElementById("messageStatus").textContent="Sélectionne le texte puis copie-le manuellement.";
    document.getElementById("messageStatus").className="status warn";
  }
}

window.addEventListener("load",boot);
</script>
</body>
</html>"""


def dashboard_response() -> HTMLResponse:
    return HTMLResponse(DASHBOARD_HTML)
