let CACHED_BARBERS = [];
let CACHED_SERVICES = [];
let LAST_LOOKUP_RESULT = null;

function langHeaders(extra={}) {
  return {"X-Lang":getCurrentLang(),...extra};
}

function showMsg(id,text,type) {
  const el=document.getElementById(id);
  el.textContent=text; el.className="msg "+type; el.style.display="block";
  setTimeout(()=>{el.style.display="none";},5000);
}

function formatDate(d) { const [y,m,dd]=d.split("-"); return `${dd}/${m}/${y}`; }

function mostrarAba(tab,event) {
  document.querySelectorAll(".aba").forEach(el=>el.classList.remove("ativa"));
  document.querySelectorAll(".nav-btn").forEach(el=>el.classList.remove("active"));
  document.getElementById("aba-"+tab).classList.add("ativa");
  if(event) event.currentTarget.classList.add("active");
}

async function loadBarbersAndServices() {
  const [br,sr]=await Promise.all([
    fetch(API_BASE+"/api/public/barbers"),
    fetch(API_BASE+"/api/public/services",{headers:langHeaders()}),
  ]);
  CACHED_BARBERS=await br.json();
  CACHED_SERVICES=await sr.json();
  renderBarberOptions();
  renderServiceOptions();
}

function renderBarberOptions() {
  const sel=document.getElementById("barber_id");
  const prev=sel.value;
  sel.innerHTML=`<option value="">${t("placeholder_select_barber")}</option>`;
  CACHED_BARBERS.forEach(b=>{
    const o=document.createElement("option");
    o.value=b.id; o.textContent=b.name; sel.appendChild(o);
  });
  if(prev) sel.value=prev;
}

function renderServiceOptions() {
  const sel=document.getElementById("service_id");
  const prev=sel.value;
  sel.innerHTML=`<option value="">${t("placeholder_select_service")}</option>`;
  CACHED_SERVICES.forEach(s=>{
    const o=document.createElement("option");
    o.value=s.id;
    o.textContent=`${s.name} — R$ ${Number(s.price).toFixed(2)} · ${s.duration_minutes}min`;
    sel.appendChild(o);
  });
  if(prev) sel.value=prev;
}

async function updateAvailableTimes() {
  const barberId=document.getElementById("barber_id").value;
  const date=document.getElementById("date").value;
  const timeSelect=document.getElementById("time");
  if(!barberId||!date){
    timeSelect.innerHTML=`<option value="">${t("placeholder_select_date_first")}</option>`; return;
  }
  const res=await fetch(API_BASE+`/api/public/availability?barber_id=${barberId}&date=${date}`);
  const data=await res.json();
  timeSelect.innerHTML="";
  if(!data.slots||data.slots.length===0){
    timeSelect.innerHTML=`<option value="">${t("msg_no_slots")}</option>`; return;
  }
  data.slots.forEach(s=>{
    const o=document.createElement("option");
    o.value=s; o.textContent=s; timeSelect.appendChild(o);
  });
}

async function bookAppointment() {
  const client_name=document.getElementById("client_name").value.trim();
  const client_phone=document.getElementById("client_phone").value.trim();
  const client_email=document.getElementById("client_email").value.trim();
  const barber_id=document.getElementById("barber_id").value;
  const service_id=document.getElementById("service_id").value;
  const date=document.getElementById("date").value;
  const time=document.getElementById("time").value;

  document.getElementById("confirmation-box").style.display="none";
  document.getElementById("confirmation-box").innerHTML="";

  if(!client_name||!client_phone||!barber_id||!service_id||!date||!time){
    showMsg("msg-form",t("msg_fill_required"),"erro"); return;
  }

  const payload={client_name,client_phone,barber_id,service_id,date,time};
  if(client_email) payload.client_email=client_email;

  const res=await fetch(API_BASE+"/api/public/appointments",{
    method:"POST",
    headers:langHeaders({"Content-Type":"application/json"}),
    body:JSON.stringify(payload),
  });

  if(res.ok){
    const created=await res.json();
    renderBookingConfirmation(client_name,time,created.confirmation_code);
    document.getElementById("client_name").value="";
    document.getElementById("client_phone").value="";
    document.getElementById("client_email").value="";
    document.getElementById("date").value="";
    await updateAvailableTimes();
  } else {
    const err=await res.json();
    showMsg("msg-form",err.detail||t("msg_booking_error"),"erro");
  }
}

function renderBookingConfirmation(clientName,time,confirmationCode) {
  const box=document.getElementById("confirmation-box");
  box.style.display="block";
  box.dataset.cachedName=clientName;
  box.dataset.cachedTime=time;
  box.dataset.cachedCode=confirmationCode;
  box.innerHTML=`
    <div class="msg sucesso" style="display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap;">
      <span>${t("msg_booking_confirmed")} ${esc(clientName)} — ${esc(time)}</span>
      <span class="confirmation-code" style="margin:0;">
        <span class="code-label">${t("label_your_code")}</span>
        <span class="code-value">${confirmationCode}</span>
      </span>
    </div>
    <p style="font-size:13px;color:var(--ink-soft);margin-top:10px;">${t("msg_save_code_hint")}</p>
  `;
  clearTimeout(box._hideTimeout);
  box._hideTimeout=setTimeout(()=>{
    box.style.display="none"; box.innerHTML="";
    delete box.dataset.cachedName; delete box.dataset.cachedTime; delete box.dataset.cachedCode;
  },60000);
}

async function lookupAppointment() {
  const client_phone=document.getElementById("lookup_phone").value.trim();
  const confirmation_code=document.getElementById("lookup_code").value.trim();
  if(!client_phone||!confirmation_code){showMsg("msg-lookup",t("msg_fill_required"),"erro");return;}

  const res=await fetch(API_BASE+"/api/public/appointments/lookup",{
    method:"POST",
    headers:langHeaders({"Content-Type":"application/json"}),
    body:JSON.stringify({client_phone,confirmation_code}),
  });

  if(!res.ok){const err=await res.json();showMsg("msg-lookup",err.detail||t("msg_appointment_not_found"),"erro");return;}
  const appointment=await res.json();
  LAST_LOOKUP_RESULT=appointment;
  renderLookupResult(appointment);
}

function renderLookupResult(a) {
  document.getElementById("lookup-form-card").style.display="none";
  document.getElementById("lookup-result-card").style.display="block";

  const statusClass=`status-${a.status}`;
  const statusLabel=t(`status_${a.status}`);
  const serviceName=a.services?a.services.name:"";
  const barberName=a.barbers?a.barbers.name:"";
  const canCancel=a.status==="scheduled";
  const canReschedule=a.status==="scheduled"&&(a.reschedule_count||0)<3;
  const rescheduleCount=a.reschedule_count||0;

  document.getElementById("lookup-result").innerHTML=`
    <div class="ficha" style="border-bottom:none;padding-top:0;">
      <div class="ficha-numero">
        ${a.time.slice(0,5)}
        <small>${formatDate(a.date)}</small>
      </div>
      <div class="ficha-info">
        <strong>${esc(serviceName)}</strong>
        <span>${t("with_barber")} ${esc(barberName)}</span>
        <div class="ficha-meta"><span>📞 ${esc(a.client_phone)}</span></div>
        <span class="status-tag ${statusClass}" style="margin-top:8px;">${statusLabel}</span>
        ${rescheduleCount>0?`<span style="font-size:12px;color:var(--ink-soft);margin-top:4px;">${t("reschedule_count_label")}: ${rescheduleCount}/3</span>`:""}
      </div>
    </div>
    ${canReschedule?`
      <div id="reschedule-section" style="margin-top:16px;">
        <button class="btn-secondary" style="width:100%;margin-bottom:12px;" onclick="toggleRescheduleForm()">${t("btn_reschedule")}</button>
        <div id="reschedule-form" style="display:none;">
          <div class="form-grid">
            <div class="form-group">
              <label>${t("label_new_date")}</label>
              <input type="date" id="reschedule-date" min="${new Date().toISOString().split('T')[0]}" onchange="loadRescheduleSlotsPublic('${a.barber_id||""}')" />
            </div>
            <div class="form-group">
              <label>${t("label_new_time")}</label>
              <select id="reschedule-time"></select>
            </div>
          </div>
          <div style="display:flex;gap:8px;margin-top:8px;">
            <button class="btn-primary" style="flex:1;" onclick="confirmReschedulePublic('${a.id}')">${t("btn_confirm_reschedule")}</button>
            <button class="btn-secondary" onclick="toggleRescheduleForm()">${t("btn_cancel_reschedule")}</button>
          </div>
          <div id="msg-reschedule" class="msg" style="display:none;margin-top:8px;"></div>
        </div>
      </div>
    `:""}
    ${canCancel?`<button class="btn-secondary" style="margin-top:12px;width:100%;" onclick="cancelLookedUpAppointment('${a.id}')">${t("btn_cancel_appointment")}</button>`:""}
  `;
}

function toggleRescheduleForm() {
  const form=document.getElementById("reschedule-form");
  form.style.display=form.style.display==="none"?"block":"none";
}

async function loadRescheduleSlotsPublic(barberId) {
  const date=document.getElementById("reschedule-date").value;
  if(!date||!barberId) return;
  const res=await fetch(API_BASE+`/api/public/availability?barber_id=${barberId}&date=${date}`);
  const data=await res.json();
  const sel=document.getElementById("reschedule-time");
  sel.innerHTML="";
  (data.slots||[]).forEach(s=>{
    const o=document.createElement("option"); o.value=s; o.textContent=s; sel.appendChild(o);
  });
  if(!data.slots||data.slots.length===0){
    sel.innerHTML=`<option>${t("msg_no_slots")}</option>`;
  }
}

async function confirmReschedulePublic(appointmentId) {
  const client_phone=document.getElementById("lookup_phone").value.trim();
  const confirmation_code=document.getElementById("lookup_code").value.trim();
  const date=document.getElementById("reschedule-date").value;
  const time=document.getElementById("reschedule-time").value;
  const msgEl=document.getElementById("msg-reschedule");

  if(!date||!time){
    msgEl.textContent=t("msg_fill_required"); msgEl.className="msg erro"; msgEl.style.display="block"; return;
  }

  const res=await fetch(API_BASE+`/api/public/appointments/${appointmentId}/reschedule`,{
    method:"PUT",
    headers:langHeaders({"Content-Type":"application/json"}),
    body:JSON.stringify({date,time,client_phone,confirmation_code}),
  });

  if(res.ok){
    const updated=await res.json();
    LAST_LOOKUP_RESULT=updated;
    msgEl.textContent=t("msg_reschedule_success"); msgEl.className="msg sucesso"; msgEl.style.display="block";
    setTimeout(()=>renderLookupResult(updated),1000);
  } else {
    const err=await res.json().catch(()=>({}));
    msgEl.textContent=err.detail||t("msg_reschedule_error"); msgEl.className="msg erro"; msgEl.style.display="block";
  }
}

async function cancelLookedUpAppointment(appointmentId) {
  if(!confirm(t("msg_confirm_cancel"))) return;
  const client_phone=document.getElementById("lookup_phone").value.trim();
  const confirmation_code=document.getElementById("lookup_code").value.trim();
  const res=await fetch(API_BASE+`/api/public/appointments/${appointmentId}/cancel`,{
    method:"POST",
    headers:langHeaders({"Content-Type":"application/json"}),
    body:JSON.stringify({client_phone,confirmation_code}),
  });
  if(res.ok){const updated=await res.json();LAST_LOOKUP_RESULT=updated;renderLookupResult(updated);}
  else{const err=await res.json();alert(err.detail||t("msg_booking_error"));}
}

function resetLookup() {
  document.getElementById("lookup-form-card").style.display="block";
  document.getElementById("lookup-result-card").style.display="none";
  document.getElementById("lookup_phone").value="";
  document.getElementById("lookup_code").value="";
  LAST_LOOKUP_RESULT=null;
}

document.addEventListener("DOMContentLoaded",async()=>{
  await loadBarbersAndServices();
  document.getElementById("date").min=new Date().toISOString().split("T")[0];
});

document.getElementById("barber_id")?.addEventListener("change",updateAvailableTimes);
document.getElementById("date")?.addEventListener("change",updateAvailableTimes);

document.addEventListener("langchange",async()=>{
  await loadBarbersAndServices();
  const box=document.getElementById("confirmation-box");
  if(box&&box.style.display!=="none"&&box.dataset.cachedCode){
    renderBookingConfirmation(box.dataset.cachedName,box.dataset.cachedTime,box.dataset.cachedCode);
  }
  const resultCard=document.getElementById("lookup-result-card");
  if(resultCard&&resultCard.style.display!=="none"&&LAST_LOOKUP_RESULT){
    await lookupAppointmentSilently();
  }
});

async function lookupAppointmentSilently() {
  const client_phone=document.getElementById("lookup_phone").value.trim();
  const confirmation_code=document.getElementById("lookup_code").value.trim();
  if(!client_phone||!confirmation_code) return;
  const res=await fetch(API_BASE+"/api/public/appointments/lookup",{
    method:"POST",
    headers:langHeaders({"Content-Type":"application/json"}),
    body:JSON.stringify({client_phone,confirmation_code}),
  });
  if(res.ok){const a=await res.json();LAST_LOOKUP_RESULT=a;renderLookupResult(a);}
}
