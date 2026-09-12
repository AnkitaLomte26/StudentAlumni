document.addEventListener("DOMContentLoaded", async () => {
  const status = document.getElementById("page-status");
  const list = document.getElementById("verification-list");
  const proofDialog = document.getElementById("proof-dialog");
  const proofImage = document.getElementById("proof-image");
  const proofPdf = document.getElementById("proof-pdf");
  const proofStatus = document.getElementById("proof-status");
  let proofUrl = null, proofTrigger = null;
  let page = 1, loading = false;
  const catalogDefinitions = [
    {key:"companies", title:"Companies", singular:"Company"},
    {key:"skills", title:"Skills", singular:"Skill"},
    {key:"guidance-areas", title:"Guidance areas", singular:"Guidance area"},
  ];
  const previous = document.getElementById("previous-page"), next = document.getElementById("next-page");
  function clearProof() {
    proofImage.hidden=true; proofImage.removeAttribute("src"); proofImage.alt="";
    proofPdf.hidden=true; proofPdf.removeAttribute("src");
    if(proofUrl){URL.revokeObjectURL(proofUrl);proofUrl=null;}
    setStatus(proofStatus,"");
  }
  document.getElementById("close-proof").addEventListener("click",()=>proofDialog.close());
  proofDialog.addEventListener("close",()=>{clearProof();if(proofTrigger?.isConnected)proofTrigger.focus();proofTrigger=null;});
  window.addEventListener("pagehide",clearProof);
  async function openProof(item, button, localStatus) {
    await action(button,localStatus,async()=>{
      const response=await fetch(API_BASE+"/api/admin/verifications/"+item.user_id+"/proof",{credentials:"include",cache:"no-store"});
      if(!response.ok){
        let message="Proof file is unavailable. Ask the alumni to upload it again.";
        try{const body=await response.json();if(body.detail)message=body.detail;}catch{}
        const error=new Error(message);error.status=response.status;throw error;
      }
      const media=(response.headers.get("Content-Type")||"").split(";",1)[0].toLowerCase();
      if(!["image/png","image/jpeg","application/pdf"].includes(media))throw new Error("This proof format cannot be previewed safely.");
      clearProof(); proofUrl=URL.createObjectURL(await response.blob()); proofTrigger=button;
      document.getElementById("proof-dialog-title").textContent="College ID proof for "+item.name;
      if(media==="application/pdf"){proofPdf.src=proofUrl;proofPdf.hidden=false;}
      else{proofImage.src=proofUrl;proofImage.alt="College ID proof submitted by "+item.name;proofImage.hidden=false;}
      proofDialog.showModal();setStatus(proofStatus,media==="application/pdf"?"PDF proof loaded.":"Image proof loaded.","success");
    });
  }
  async function load() {
    if (loading) return;
    loading = true; previous.disabled = next.disabled = true;
    try {
      setStatus(status,"Loading pending verifications…");
      const data = await api("/api/admin/verifications?page=" + page);
      list.replaceChildren();
      if (!data.items.length) list.append(el("p","No pending proofs to review.","card empty-state"));
      data.items.forEach(item => {
        const card = el("article","","card review-card");
        card.append(el("h2",item.name),el("p",item.email,"muted"),
          el("p",[item.branch || "Branch not added",item.graduation_year || "Year not added"].join(" · "),"small"),
          el("p","Submitted " + new Date(item.submitted_at).toLocaleString(),"small muted"));
        const proof = el("button",item.proof_media_type==="application/pdf"?"Open PDF proof":"View college ID","secondary"); proof.type="button";
        const proofFeedback=el("p","","status");proofFeedback.setAttribute("role","status");proofFeedback.setAttribute("aria-live","polite");
        proof.addEventListener("click",()=>openProof(item,proof,proofFeedback));
        card.append(proof,proofFeedback);
        const form = el("form");
        const label = el("label","Review notes (required when rejecting)");
        const reason = document.createElement("textarea"); reason.id="reason-" + item.user_id; reason.maxLength=500; reason.rows=2; label.htmlFor=reason.id;
        const decisions = document.createElement("select"); decisions.id="decision-" + item.user_id;
        const decisionLabel=el("label","Decision"); decisionLabel.htmlFor=decisions.id;
        for (const [value,text] of [["","Choose a decision"],["VERIFIED","Approve college identity"],["REJECTED","Reject — request a new proof"]]) {
          const option=el("option",text); option.value=value; decisions.append(option);
        }
        decisions.required=true;
        const submit=el("button","Save verification decision"); submit.type="submit";
        const localStatus=el("p","","status"); localStatus.setAttribute("role","status");
        form.append(label,reason,decisionLabel,decisions,submit,localStatus);
        form.addEventListener("submit",event=>{
          event.preventDefault();
          action(submit,localStatus,async()=>{
            if(decisions.value==="REJECTED"&&!reason.value.trim())throw new Error("Give a reason so the alumni can correct their proof.");
            await api("/api/admin/verifications/"+item.user_id+"/review",{method:"POST",body:JSON.stringify({decision:decisions.value,reason:reason.value.trim()||null})});
            await load();setStatus(status,"Decision saved. The proof has been deleted.","success");
          });
        });
        card.append(form); list.append(card);
      });
      document.getElementById("page-info").textContent=data.total_pages?"Page "+page+" of "+data.total_pages:"No pending requests";
      previous.disabled=page<=1;next.disabled=page>=data.total_pages;
      setStatus(status,data.total_results+" pending verification requests.");
    } catch(error){showError(status,error);}
    finally{loading=false;}
  }
  function catalogCard(definition) {
    const card=el("article","","card catalog-card");
    const title=el("h3",definition.title);
    const description=el("p","Search existing entries or add a new "+definition.singular.toLowerCase()+".","muted");
    const searchForm=document.createElement("form"); searchForm.className="catalog-controls"; searchForm.setAttribute("role","search");
    const searchLabel=el("label","Search "+definition.title,"sr-only");
    const search=document.createElement("input"); search.type="search"; search.maxLength=120; search.placeholder="Search "+definition.title.toLowerCase(); search.id="search-"+definition.key; searchLabel.htmlFor=search.id;
    const searchButton=el("button","Search","secondary"); searchButton.type="submit";
    const list=document.createElement("ul"); list.className="catalog-items"; list.setAttribute("aria-label",definition.title);
    const pageInfo=el("span","","small"); pageInfo.setAttribute("role","status");
    const previous=el("button","Previous","secondary"), next=el("button","Next","secondary"); previous.type=next.type="button";
    const navigation=el("nav","","pagination compact-pagination"); navigation.setAttribute("aria-label",definition.title+" pages"); navigation.append(previous,pageInfo,next);
    const addForm=document.createElement("form"); addForm.className="catalog-add";
    const addLabel=el("label","Add "+definition.singular.toLowerCase());
    const name=document.createElement("input"); name.id="add-"+definition.key; name.required=true; name.maxLength=80; name.placeholder="New "+definition.singular.toLowerCase()+" name"; addLabel.htmlFor=name.id;
    const addButton=el("button","Add "+definition.singular); addButton.type="submit";
    const feedback=el("p","","status"); feedback.setAttribute("role","status"); feedback.setAttribute("aria-live","polite");
    addForm.append(addLabel,name,addButton,feedback); searchForm.append(searchLabel,search,searchButton);
    card.append(title,description,searchForm,list,navigation,addForm);
    let currentPage=1, request=0;
    async function loadCatalog() {
      const revision=++request, offset=(currentPage-1)*20;
      previous.disabled=next.disabled=true; list.setAttribute("aria-busy","true");
      try {
        const items=await api("/api/catalogs/"+definition.key+"?q="+encodeURIComponent(search.value.trim())+"&limit=21&offset="+offset);
        if(revision!==request)return;
        const visible=items.slice(0,20); list.replaceChildren(...visible.map(item=>el("li",item.name)));
        if(!visible.length)list.append(el("li",search.value.trim()?"No matching entries.":"No entries yet.","muted"));
        const hasNext=items.length>20;
        pageInfo.textContent="Page "+currentPage; previous.disabled=currentPage<=1; next.disabled=!hasNext;
      } catch(error){showError(feedback,error);}
      finally{if(revision===request)list.setAttribute("aria-busy","false");}
    }
    searchForm.addEventListener("submit",event=>{event.preventDefault();currentPage=1;loadCatalog();});
    previous.addEventListener("click",()=>{if(currentPage>1){currentPage--;loadCatalog();}});
    next.addEventListener("click",()=>{currentPage++;loadCatalog();});
    addForm.addEventListener("submit",event=>{
      event.preventDefault();
      action(addButton,feedback,async()=>{
        const value=name.value.trim(); if(!value){name.focus();throw new Error(definition.singular+" name is required.");}
        await api("/api/catalogs/"+definition.key,{method:"POST",body:JSON.stringify({name:value})});
        name.value=""; search.value=""; currentPage=1; await loadCatalog();
        setStatus(feedback,definition.singular+" added successfully.","success");
      });
    });
    loadCatalog(); return card;
  }
  try {
    if(!await pageUser("ADMIN"))return;
    pageLogout();document.getElementById("admin-content").hidden=false;
    document.getElementById("catalog-management").replaceChildren(...catalogDefinitions.map(catalogCard));
    previous.addEventListener("click",()=>{page--;load();});
    next.addEventListener("click",()=>{page++;load();});
    document.getElementById("refresh-queue").addEventListener("click",()=>{page=1;load();});
    await load();
  } catch(error){showError(status,error);}
});
