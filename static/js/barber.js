const WEEKDAYS = [0,1,2,3,4,5,6];
let CURRENT_BARBER_TAB = "appointments";

function showMsg(id, text, type) {
  const el=document.getElementById(id);
  el.textContent=text; el.className="msg "+type; el.style.display="block";
  setTimeout(()=>{el.style.display="none";},5000);
}
function formatDate(d) { const [y,m,dd]=d.split("-"); return `${dd}/${m}/${y}`; }

async function authFetch(url, options={}) {
  // Session lives in the HttpOnly cookie set at /login — the browser
  // attaches it automatically on same-origin requests. No token is
  // read from or written to client-side storage, so there is nothing
  // for an XSS payload to steal even if output-encoding were ever
  // bypassed elsewhere.
  const res=await fetch(url,{...options, credentials:"same-origin"});
  if(res.status===401||res.status===403){logout();throw new Error("Session expired");}
  return res;
}

function mostrarAbaBarbeiro(tab, event) {
  CURRENT_BARBER_TAB=tab;
  document.querySelectorAll(".aba").forEach(el=>el.classList.remove("ativa"));
  document.querySelectorAll(".nav-btn").forEach(el=>el.classList.remove("active"));
  document.getElementById("aba-"+tab).classList.add("ativa");
  if(event) event.currentTarget.classList.add("active");
  if(tab==="appointments"){
    const f=document.getElementById("filtro-data-barbeiro");
    if(!f.value) f.value=new Date().toISOString().split("T")[0];
    loadMyAppointments();
  } else if(tab==="my-schedule") loadSchedule();
  else if(tab==="time-off") loadTimeOff();
}

async function login() {
  const email=document.getElementById("login-email").value.trim();
  const password=document.getElementById("login-password").value;
  if(!email||!password){showMsg("msg-login",t("msg_fill_required"),"erro");return;}
  const res=await fetch(API_BASE+"/api/barber/login",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({email,password})});
  if(!res.ok){showMsg("msg-login",t("msg_login_error"),"erro");return;}
  const data=await res.json();
  if(data.mfa_required){
    // MFA step-up pending: backend already set the short-lived pending
    // cookie. Frontend UI for the 6-digit code challenge is not wired
    // up yet — tracked separately.
    showMsg("msg-login",t("msg_mfa_pending")||"MFA required.","erro");
    return;
  }
  enterDashboard();
}

async function logout() {
  try {
    await fetch(API_BASE+"/api/barber/logout", {method:"POST", credentials:"same-origin"});
  } catch(e) {
    // Best-effort: even if this call fails (network issue, already
    // expired session), still reset the UI below so the user isn't
    // stuck on a dashboard that no longer has a valid session.
  }
  document.getElementById("barber-nav").style.display="none";
  document.getElementById("login-actions").style.display="flex";
  document.querySelectorAll(".aba").forEach(el=>el.classList.remove("ativa"));
  document.getElementById("tela-login").classList.add("ativa");
}

function enterDashboard() {
  document.getElementById("tela-login").classList.remove("ativa");
  document.getElementById("barber-nav").style.display="flex";
  document.getElementById("login-actions").style.display="none";
  document.getElementById("aba-appointments").classList.add("ativa");
  CURRENT_BARBER_TAB="appointments";
  const f=document.getElementById("filtro-data-barbeiro");
  f.value=new Date().toISOString().split("T")[0];
  loadMyAppointments();
}

async function loadMyAppointments() {
  const date=document.getElementById("filtro-data-barbeiro").value;
  const lista=document.getElementById("lista-appointments-barbeiro");
  if(!date){lista.innerHTML=`<p class="vazio">${t("agenda_empty")}</p>`;lista.dataset.cachedJson="";return;}
  const res=await authFetch(API_BASE+`/api/barber/appointments?date=${date}`,{headers:{"X-Lang":getCurrentLang()}});
  const appointments=await res.json();
  renderMyAppointments(appointments);
}

function renderMyAppointments(appointments) {
  const lista=document.getElementById("lista-appointments-barbeiro");
  if(!appointments||appointments.length===0){
    lista.innerHTML=`<p class="vazio">${t("agenda_empty_for_date")}</p>`;
    lista.dataset.cachedJson=""; return;
  }

  const now=new Date();
  const todayStr=now.toISOString().split("T")[0];
  const nowTime=now.getHours()*60+now.getMinutes();

  let nextId=null;
  for(const a of appointments){
    if(a.status==="scheduled"){
      const [h,m]=a.time.split(":").map(Number);
      if(a.date===todayStr&&h*60+m>=nowTime){nextId=a.id;break;}
    }
  }

  lista.innerHTML=appointments.map(a=>{
    const statusClass=`status-${a.status}`;
    const statusLabel=t(`status_${a.status}`);
    const serviceName=a.services?a.services.name:"";
    const isNext=a.id===nextId;
    let delayBadge="";
    if(a.status==="scheduled"&&a.date===todayStr){
      const [h,m]=a.time.split(":").map(Number);
      if(h*60+m<nowTime) delayBadge=`<span class="status-tag status-cancelled" style="margin-left:6px;">${t("label_delayed")}</span>`;
    }
    return `
      <div class="ficha${isNext?" ficha-next":""}" id="item-${a.id}">
        <div class="ficha-numero">
          ${a.time.slice(0,5)}
          ${isNext?`<small style="color:var(--ledger);font-size:10px;">${t("label_next_client")}</small>`:""}
        </div>
        <div class="ficha-info">
          <strong>${esc(a.client_name)}</strong>
          <span>${esc(serviceName)}</span>
          <div class="ficha-meta">
            <span>📞 ${esc(a.client_phone)}</span>
            ${a.client_email?`<span>✉️ ${esc(a.client_email)}</span>`:""}
          </div>
          <div style="display:flex;align-items:center;gap:6px;margin-top:6px;flex-wrap:wrap;">
            <span class="status-tag ${statusClass}">${statusLabel}</span>
            ${delayBadge}
          </div>
          ${a.notes&&!a.notes.startsWith("[ip:")?`<div style="margin-top:6px;font-size:13px;color:var(--ink-soft);">📝 ${esc(a.notes)}</div>`:""}
          <div class="notes-form" id="notes-form-${a.id}" style="margin-top:8px;display:none;">
            <textarea id="notes-input-${a.id}" placeholder="${t("placeholder_notes")}" style="width:100%;min-height:60px;font-size:13px;padding:6px;border:1px solid var(--line);border-radius:var(--radius);background:var(--surface);color:var(--ink);resize:vertical;">${a.notes&&!a.notes.startsWith("[ip:")?esc(a.notes):""}</textarea>
            <div style="display:flex;gap:6px;margin-top:6px;">
              <button class="btn-secondary" style="font-size:12px;padding:4px 10px;" onclick="saveNotes('${a.id}')">${t("btn_save_notes")}</button>
              <button class="btn-secondary" style="font-size:12px;padding:4px 10px;" onclick="toggleNotes('${a.id}',false)">✕</button>
            </div>
          </div>
        </div>
        <div class="ficha-acoes">
          ${a.status==="scheduled"?`
            <button class="btn-icon edit" title="${t("btn_mark_completed")}" onclick="updateStatus('${a.id}','completed')">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><polyline points="20 6 9 17 4 12"/></svg>
            </button>
            <button class="btn-icon" title="${t("btn_reschedule_barber")}" onclick="openRescheduleBarber('${a.id}')" style="color:var(--ink-soft);">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>
            </button>
            <button class="btn-icon" title="${t("label_notes")}" onclick="toggleNotes('${a.id}',true)" style="color:var(--ink-soft);">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>
            </button>
            <button class="btn-icon del" title="${t("btn_cancel_appointment")}" onclick="updateStatus('${a.id}','cancelled')">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
            </button>
          `:""}
        </div>
      </div>
      <div id="reschedule-barber-${a.id}" style="display:none;padding:12px 0 4px;border-bottom:1px solid var(--line);">
        <div style="display:flex;gap:8px;align-items:flex-end;flex-wrap:wrap;">
          <div class="form-group" style="margin:0;">
            <label style="font-size:12px;">${t("label_new_date")}</label>
            <input type="date" id="rb-date-${a.id}" min="${new Date().toISOString().split('T')[0]}" style="font-size:13px;" />
          </div>
          <div class="form-group" style="margin:0;">
            <label style="font-size:12px;">${t("label_new_time")}</label>
            <select id="rb-time-${a.id}" style="font-size:13px;"></select>
          </div>
          <button class="btn-secondary" style="font-size:12px;" onclick="confirmRescheduleBarber('${a.id}')">${t("btn_confirm_reschedule")}</button>
          <button class="btn-secondary" style="font-size:12px;" onclick="closeRescheduleBarber('${a.id}')">${t("btn_cancel_reschedule")}</button>
        </div>
        <div id="rb-msg-${a.id}" class="msg" style="display:none;margin-top:6px;"></div>
      </div>
    `;
  }).join("");

  lista.dataset.cachedJson=JSON.stringify(appointments);

  appointments.forEach(a=>{
    const dateInput=document.getElementById(`rb-date-${a.id}`);
    if(dateInput) dateInput.addEventListener("change",()=>loadRescheduleSlots(a.id));
  });
}

function toggleNotes(apptId,show) {
  const form=document.getElementById(`notes-form-${apptId}`);
  if(form) form.style.display=show?"block":"none";
}

async function saveNotes(apptId) {
  const notes=document.getElementById(`notes-input-${apptId}`).value.trim();
  const res=await authFetch(API_BASE+`/api/barber/appointments/${apptId}`,{
    method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({notes})
  });
  if(res.ok){toggleNotes(apptId,false);loadMyAppointments();}
  else alert(t("msg_booking_error"));
}

async function updateStatus(appointmentId,status) {
  const res=await authFetch(API_BASE+`/api/barber/appointments/${appointmentId}`,{
    method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({status})
  });
  if(res.ok){loadMyAppointments();}
  else{const err=await res.json().catch(()=>({}));alert(err.detail||t("msg_booking_error"));}
}

async function openRescheduleBarber(apptId) {
  document.getElementById(`reschedule-barber-${apptId}`).style.display="block";
}

function closeRescheduleBarber(apptId) {
  document.getElementById(`reschedule-barber-${apptId}`).style.display="none";
}

async function loadRescheduleSlots(apptId) {
  const lista=document.getElementById("lista-appointments-barbeiro");
  const cached=lista.dataset.cachedJson?JSON.parse(lista.dataset.cachedJson):[];
  const appt=cached.find(a=>a.id===apptId);
  if(!appt||!appt.barber_id) return;
  const date=document.getElementById(`rb-date-${apptId}`).value;
  if(!date) return;
  const res=await fetch(API_BASE+`/api/public/availability?barber_id=${appt.barber_id}&date=${date}`);
  const data=await res.json();
  const sel=document.getElementById(`rb-time-${apptId}`);
  sel.innerHTML="";
  (data.slots||[]).forEach(s=>{
    const o=document.createElement("option"); o.value=s; o.textContent=s; sel.appendChild(o);
  });
  if(!data.slots||data.slots.length===0) sel.innerHTML=`<option>${t("msg_no_slots")}</option>`;
}

async function confirmRescheduleBarber(apptId) {
  const date=document.getElementById(`rb-date-${apptId}`).value;
  const time=document.getElementById(`rb-time-${apptId}`).value;
  if(!date||!time){alert(t("msg_fill_required"));return;}
  const res=await authFetch(API_BASE+`/api/barber/appointments/${apptId}/reschedule`,{
    method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({date,time})
  });
  const msgEl=document.getElementById(`rb-msg-${apptId}`);
  if(res.ok){
    msgEl.textContent=t("msg_reschedule_success"); msgEl.className="msg sucesso"; msgEl.style.display="block";
    setTimeout(()=>loadMyAppointments(),1000);
  } else {
    const err=await res.json().catch(()=>({}));
    msgEl.textContent=err.detail||t("msg_reschedule_error"); msgEl.className="msg erro"; msgEl.style.display="block";
  }
}

async function loadSchedule() {
  const res=await authFetch(API_BASE+"/api/barber/schedule");
  renderSchedule(await res.json());
}

function renderSchedule(schedule) {
  const byWeekday={};
  (schedule||[]).forEach(s=>{byWeekday[s.weekday]=s;});
  const container=document.getElementById("grade-horarios");
  container.dataset.cachedJson=JSON.stringify(schedule||[]);
  container.innerHTML=WEEKDAYS.map(day=>{
    const e=byWeekday[day];
    return `
      <div class="schedule-row" data-weekday="${day}">
        <input type="checkbox" class="day-active" ${e?"checked":""} />
        <label class="weekday-label">${t("weekday_"+day)}</label>
        <input type="time" class="day-start" value="${e?e.start_time.slice(0,5):"09:00"}" />
        <span>—</span>
        <input type="time" class="day-end" value="${e?e.end_time.slice(0,5):"18:00"}" />
        <input type="number" class="day-slot" value="${e?e.slot_minutes:30}" title="${t("label_slot_duration")}" />
        <span style="font-size:12px;color:var(--ink-soft);">${t("label_slot_duration")}</span>
      </div>`;
  }).join("");
}

function rerenderScheduleKeepingCurrentValues() {
  const rows=document.querySelectorAll(".schedule-row");
  const state=Array.from(rows).map(r=>({
    weekday:parseInt(r.getAttribute("data-weekday"),10),
    active:r.querySelector(".day-active").checked,
    start:r.querySelector(".day-start").value,
    end:r.querySelector(".day-end").value,
    slot:r.querySelector(".day-slot").value,
  }));
  const container=document.getElementById("grade-horarios");
  container.innerHTML=WEEKDAYS.map(day=>{
    const s=state.find(x=>x.weekday===day);
    return `
      <div class="schedule-row" data-weekday="${day}">
        <input type="checkbox" class="day-active" ${s&&s.active?"checked":""} />
        <label class="weekday-label">${t("weekday_"+day)}</label>
        <input type="time" class="day-start" value="${s?s.start:"09:00"}" />
        <span>—</span>
        <input type="time" class="day-end" value="${s?s.end:"18:00"}" />
        <input type="number" class="day-slot" value="${s?s.slot:30}" title="${t("label_slot_duration")}" />
        <span style="font-size:12px;color:var(--ink-soft);">${t("label_slot_duration")}</span>
      </div>`;
  }).join("");
}

async function saveSchedule() {
  const rows=document.querySelectorAll(".schedule-row");
  const slots=[];
  rows.forEach(row=>{
    if(!row.querySelector(".day-active").checked) return;
    slots.push({
      weekday:parseInt(row.getAttribute("data-weekday"),10),
      start_time:row.querySelector(".day-start").value,
      end_time:row.querySelector(".day-end").value,
      slot_minutes:parseInt(row.querySelector(".day-slot").value,10)||30,
    });
  });
  const res=await authFetch(API_BASE+"/api/barber/schedule",{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify(slots)});
  if(res.ok) alert(t("btn_save_schedule")+" ✓");
  else alert(t("msg_booking_error"));
}

async function loadTimeOff() {
  const res=await authFetch(API_BASE+"/api/barber/time-off");
  renderTimeOff(await res.json());
}

function renderTimeOff(items) {
  const lista=document.getElementById("lista-time-off");
  if(!items||items.length===0){lista.innerHTML=`<p class="vazio">${t("agenda_empty_for_date")}</p>`;lista.dataset.cachedJson="";return;}
  lista.innerHTML=items.map(item=>`
    <div class="list-row" id="timeoff-${item.id}">
      <div class="list-row-info">
        <strong>${formatDate(item.date)}</strong>
        <span>${item.start_time?`${item.start_time.slice(0,5)} - ${item.end_time.slice(0,5)}`:t("agenda_empty_for_date")}</span>
        ${item.reason?`<span>${esc(item.reason)}</span>`:""}
      </div>
      <div class="list-row-actions">
        <button class="btn-icon del" onclick="deleteTimeOff('${item.id}')">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14H6L5 6"/></svg>
        </button>
      </div>
    </div>`).join("");
  lista.dataset.cachedJson=JSON.stringify(items);
}

async function addTimeOff() {
  const date=document.getElementById("timeoff-date").value;
  if(!date) return;
  const payload={date};
  const s=document.getElementById("timeoff-start").value;
  const e=document.getElementById("timeoff-end").value;
  const r=document.getElementById("timeoff-reason").value.trim();
  if(s) payload.start_time=s;
  if(e) payload.end_time=e;
  if(r) payload.reason=r;
  const res=await authFetch(API_BASE+"/api/barber/time-off",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
  if(res.ok){
    ["timeoff-date","timeoff-start","timeoff-end","timeoff-reason"].forEach(id=>document.getElementById(id).value="");
    loadTimeOff();
  }
}

async function deleteTimeOff(id) {
  const res=await authFetch(API_BASE+`/api/barber/time-off/${id}`,{method:"DELETE"});
  if(res.ok||res.status===204) document.getElementById(`timeoff-${id}`)?.remove();
}

document.addEventListener("langchange",()=>{
  if(CURRENT_BARBER_TAB==="appointments"){
    const lista=document.getElementById("lista-appointments-barbeiro");
    if(lista&&lista.dataset.cachedJson) renderMyAppointments(JSON.parse(lista.dataset.cachedJson));
  } else if(CURRENT_BARBER_TAB==="my-schedule"){
    rerenderScheduleKeepingCurrentValues();
  } else if(CURRENT_BARBER_TAB==="time-off"){
    const lista=document.getElementById("lista-time-off");
    if(lista&&lista.dataset.cachedJson) renderTimeOff(JSON.parse(lista.dataset.cachedJson));
  }
});

document.addEventListener("DOMContentLoaded",async()=>{
  try {
    const res=await fetch(API_BASE+"/api/barber/me",{credentials:"same-origin"});
    if(res.ok) enterDashboard();
  } catch(e) { /* no valid session cookie — stay on login screen */ }
});
