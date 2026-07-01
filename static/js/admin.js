let CURRENT_ADMIN_TAB = "dashboard";
let LAST_DASHBOARD_DATA = null;
let CACHED_BARBERS_ADMIN = [];

function getAdminKey() { return localStorage.getItem("barbershop_admin_key"); }
function setAdminKey(k) { localStorage.setItem("barbershop_admin_key", k); }
function clearAdminKey() { localStorage.removeItem("barbershop_admin_key"); }

function showMsg(id, text, type) {
  const el=document.getElementById(id);
  el.textContent=text; el.className="msg "+type; el.style.display="block";
  setTimeout(()=>{el.style.display="none";},5000);
}
function formatDate(d) { const [y,m,dd]=d.split("-"); return `${dd}/${m}/${y}`; }
function formatCurrency(v) { return `R$ ${Number(v).toFixed(2).replace(".",",")}`; }

async function adminFetch(url, options={}) {
  const headers={...(options.headers||{}), "X-Admin-Key":getAdminKey()};
  const res=await fetch(url,{...options,headers});
  if(res.status===401){clearAdminKey();showAdminLogin();throw new Error("Invalid admin key");}
  return res;
}

function mostrarAbaAdmin(tab, event) {
  CURRENT_ADMIN_TAB=tab;
  document.querySelectorAll(".aba").forEach(el=>el.classList.remove("ativa"));
  document.querySelectorAll(".nav-btn").forEach(el=>el.classList.remove("active"));
  document.getElementById("aba-"+tab).classList.add("ativa");
  if(event) event.currentTarget.classList.add("active");
  if(tab==="dashboard") loadDashboard();
  if(tab==="appointments-admin") loadAdminAppointments();
  if(tab==="barbers") loadBarbers();
  if(tab==="services") loadServices();
}

async function adminLogin() {
  const key=document.getElementById("admin-key").value.trim();
  if(!key) return;
  setAdminKey(key);
  const res=await fetch(API_BASE+"/api/admin/barbers",{headers:{"X-Admin-Key":key}});
  if(!res.ok){clearAdminKey();showMsg("msg-admin-login",t("msg_login_error"),"erro");return;}
  enterAdminDashboard();
}

function showAdminLogin() {
  document.getElementById("admin-nav").style.display="none";
  document.getElementById("login-actions").style.display="flex";
  document.querySelectorAll(".aba").forEach(el=>el.classList.remove("ativa"));
  document.getElementById("tela-admin-login").classList.add("ativa");
}

function enterAdminDashboard() {
  document.getElementById("tela-admin-login").classList.remove("ativa");
  document.getElementById("admin-nav").style.display="flex";
  document.getElementById("login-actions").style.display="none";
  document.getElementById("aba-dashboard").classList.add("ativa");
  CURRENT_ADMIN_TAB="dashboard";
  const today=new Date();
  const ago=new Date(); ago.setDate(today.getDate()-30);
  document.getElementById("dashboard-end").value=today.toISOString().split("T")[0];
  document.getElementById("dashboard-start").value=ago.toISOString().split("T")[0];
  loadDashboard();
  loadBarbersForFilter();
}

async function loadBarbersForFilter() {
  try {
    const res=await adminFetch(API_BASE+"/api/admin/barbers");
    CACHED_BARBERS_ADMIN=await res.json();
    const sel=document.getElementById("filter-appt-barber");
    if(!sel) return;
    sel.innerHTML=`<option value="">${t("all_barbers")}</option>`;
    CACHED_BARBERS_ADMIN.forEach(b=>{
      const o=document.createElement("option"); o.value=b.id; o.textContent=b.name; sel.appendChild(o);
    });
  } catch(e){}
}

async function loadDashboard() {
  const startDate=document.getElementById("dashboard-start").value;
  const endDate=document.getElementById("dashboard-end").value;
  document.getElementById("dashboard-content").innerHTML=`<p class="vazio">${t("dashboard_loading")}</p>`;
  document.getElementById("dashboard-today").innerHTML="";
  document.getElementById("dashboard-clients").innerHTML="";
  document.getElementById("dashboard-peak").innerHTML="";

  const params=new URLSearchParams();
  if(startDate) params.set("start_date",startDate);
  if(endDate) params.set("end_date",endDate);

  try {
    const [dashRes,todayRes,clientsRes,peakRes]=await Promise.all([
      adminFetch(API_BASE+`/api/admin/reports/dashboard?${params}`),
      adminFetch(API_BASE+"/api/admin/reports/today"),
      adminFetch(API_BASE+`/api/admin/reports/clients?${params}`),
      adminFetch(API_BASE+`/api/admin/reports/peak-hours?${params}`),
    ]);
    const data=await dashRes.json();
    const today=await todayRes.json();
    const clients=await clientsRes.json();
    const peak=await peakRes.json();
    LAST_DASHBOARD_DATA={data,today,clients,peak};
    renderDashboard(data,today,clients,peak);
  } catch(e) {
    document.getElementById("dashboard-content").innerHTML=`<p class="vazio">${t("dashboard_error")}</p>`;
    LAST_DASHBOARD_DATA=null;
  }
}

function renderDashboard(data,today,clients,peak) {
  renderTodaySummary(today);
  renderMainDashboard(data);
  renderClientRanking(clients);
  renderPeakHours(peak);
}

function renderTodaySummary(today) {
  const el=document.getElementById("dashboard-today");
  el.innerHTML=`
    <h3 style="font-family:var(--font-display);font-size:18px;margin:0 0 12px;">${t("dashboard_today_title")} — ${formatDate(today.date)}</h3>
    <div class="form-grid" style="grid-template-columns:repeat(5,1fr);margin-bottom:8px;">
      ${[["dashboard_today_total",today.total],["dashboard_today_upcoming",today.upcoming],["dashboard_today_completed",today.completed],["dashboard_today_cancelled",today.cancelled],["dashboard_today_noshow",today.no_show]].map(([key,val])=>`
        <div class="list-row" style="border:1px solid var(--line);border-radius:var(--radius);flex-direction:column;align-items:flex-start;gap:4px;">
          <span class="card-eyebrow" style="margin:0;">${t(key)}</span>
          <strong style="font-family:var(--font-display);font-size:24px;">${val}</strong>
        </div>`).join("")}
    </div>`;
}

function renderMainDashboard(data) {
  const content=document.getElementById("dashboard-content");
  const summaryHtml=`
    <div class="form-grid" style="margin-bottom:8px;">
      <div class="list-row" style="border:1px solid var(--line);border-radius:var(--radius);flex-direction:column;align-items:flex-start;gap:6px;">
        <span class="card-eyebrow" style="margin:0;">${t("dashboard_total_revenue")}</span>
        <strong style="font-family:var(--font-display);font-size:28px;">${formatCurrency(data.total_revenue)}</strong>
      </div>
      <div class="list-row" style="border:1px solid var(--line);border-radius:var(--radius);flex-direction:column;align-items:flex-start;gap:6px;">
        <span class="card-eyebrow" style="margin:0;">${t("dashboard_total_appointments")}</span>
        <strong style="font-family:var(--font-display);font-size:28px;">${data.total_completed}</strong>
      </div>
    </div>`;
  if(data.total_completed===0){content.innerHTML=summaryHtml+`<p class="vazio">${t("dashboard_no_data")}</p>`;return;}
  const barberRows=data.revenue_by_barber.map(r=>`
    <div class="list-row">
      <div class="list-row-info"><strong>${esc(r.barber_name)}</strong><span>${r.count} ${t("dashboard_appointments_count")}</span></div>
      <strong style="font-family:var(--font-display);font-size:16px;">${formatCurrency(r.revenue)}</strong>
    </div>`).join("");
  const serviceRows=data.revenue_by_service.map(r=>`
    <div class="list-row">
      <div class="list-row-info"><strong>${esc(r.service_name)}</strong><span>${r.count} ${t("dashboard_appointments_count")}</span></div>
      <strong style="font-family:var(--font-display);font-size:16px;">${formatCurrency(r.revenue)}</strong>
    </div>`).join("");
  content.innerHTML=`
    ${summaryHtml}
    <h3 style="font-family:var(--font-display);font-size:18px;margin:32px 0 16px;">${t("dashboard_revenue_by_day")}</h3>
    ${renderRevenueChart(data.revenue_by_day)}
    <div class="form-grid" style="margin-top:32px;grid-template-columns:1fr 1fr;">
      <div><h3 style="font-family:var(--font-display);font-size:18px;margin:0 0 16px;">${t("dashboard_revenue_by_barber")}</h3>${barberRows||`<p class="vazio">${t("dashboard_no_data")}</p>`}</div>
      <div><h3 style="font-family:var(--font-display);font-size:18px;margin:0 0 16px;">${t("dashboard_revenue_by_service")}</h3>${serviceRows||`<p class="vazio">${t("dashboard_no_data")}</p>`}</div>
    </div>`;
}

function renderClientRanking(clients) {
  const el=document.getElementById("dashboard-clients");
  if(!clients||clients.length===0){el.innerHTML="";return;}
  el.innerHTML=`
    <h3 style="font-family:var(--font-display);font-size:18px;margin:0 0 16px;">${t("dashboard_clients_title")}</h3>
    ${clients.slice(0,10).map((c,i)=>`
      <div class="list-row">
        <div class="list-row-info">
          <strong>#${i+1} ${esc(c.client_name)}</strong>
          <span>${c.visits} ${t("dashboard_clients_visits")} · ${formatCurrency(c.total_spent)} ${t("dashboard_clients_spent")}</span>
        </div>
      </div>`).join("")}`;
}

function renderPeakHours(peak) {
  const el=document.getElementById("dashboard-peak");
  if(!peak||(!peak.by_hour.length&&!peak.by_weekday.length)){el.innerHTML="";return;}
  const maxHour=Math.max(...peak.by_hour.map(h=>h.count),1);
  const maxDay=Math.max(...peak.by_weekday.map(d=>d.count),1);
  const wdn=[t("weekday_0"),t("weekday_1"),t("weekday_2"),t("weekday_3"),t("weekday_4"),t("weekday_5"),t("weekday_6")];
  const hourBars=peak.by_hour.map(h=>`
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">
      <span style="font-size:12px;color:var(--ink-soft);width:40px;">${h.label}</span>
      <div style="flex:1;background:var(--line);border-radius:3px;height:16px;">
        <div style="width:${Math.round(h.count/maxHour*100)}%;background:var(--ledger);height:100%;border-radius:3px;"></div>
      </div>
      <span style="font-size:12px;width:24px;text-align:right;">${h.count}</span>
    </div>`).join("");
  const dayBars=peak.by_weekday.map(d=>`
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">
      <span style="font-size:12px;color:var(--ink-soft);width:56px;">${wdn[d.weekday]}</span>
      <div style="flex:1;background:var(--line);border-radius:3px;height:16px;">
        <div style="width:${Math.round(d.count/maxDay*100)}%;background:var(--ledger);height:100%;border-radius:3px;"></div>
      </div>
      <span style="font-size:12px;width:24px;text-align:right;">${d.count}</span>
    </div>`).join("");
  el.innerHTML=`
    <h3 style="font-family:var(--font-display);font-size:18px;margin:0 0 16px;">${t("dashboard_peak_title")}</h3>
    <div class="form-grid" style="grid-template-columns:1fr 1fr;">
      <div><h4 style="font-size:13px;color:var(--ink-soft);margin:0 0 10px;">${t("dashboard_peak_by_hour")}</h4>${hourBars}</div>
      <div><h4 style="font-size:13px;color:var(--ink-soft);margin:0 0 10px;">${t("dashboard_peak_by_weekday")}</h4>${dayBars}</div>
    </div>`;
}

function renderRevenueChart(revenueByDay) {
  if(!revenueByDay||revenueByDay.length===0) return `<p class="vazio">${t("dashboard_no_data")}</p>`;
  const width=100,height=40;
  const maxRevenue=Math.max(...revenueByDay.map(d=>d.revenue),1);
  const barWidth=width/revenueByDay.length;
  const barGap=barWidth*0.25;
  const bars=revenueByDay.map((day,i)=>{
    const bh=(day.revenue/maxRevenue)*(height-4);
    const x=i*barWidth+barGap/2,y=height-bh,w=barWidth-barGap;
    return `<g><title>${formatDate(day.date)}: ${formatCurrency(day.revenue)}</title><rect x="${x}" y="${y}" width="${w}" height="${bh}" rx="0.6" fill="var(--ledger)"/></g>`;
  }).join("");
  return `
    <div style="border:1px solid var(--line);border-radius:var(--radius);padding:20px;">
      <svg viewBox="0 0 ${width} ${height}" style="width:100%;height:180px;overflow:visible;" preserveAspectRatio="none">${bars}</svg>
      <div style="display:flex;justify-content:space-between;margin-top:8px;font-size:11px;color:var(--ink-soft);">
        <span>${formatDate(revenueByDay[0].date)}</span>
        <span>${formatDate(revenueByDay[revenueByDay.length-1].date)}</span>
      </div>
    </div>`;
}

async function loadAdminAppointments() {
  const date=document.getElementById("filter-appt-date").value;
  const barber_id=document.getElementById("filter-appt-barber").value;
  const status=document.getElementById("filter-appt-status").value;
  const lista=document.getElementById("lista-appointments-admin");
  lista.innerHTML=`<p class="vazio">${t("dashboard_loading")}</p>`;
  const params=new URLSearchParams();
  if(date) params.set("date",date);
  if(barber_id) params.set("barber_id",barber_id);
  if(status) params.set("status",status);
  try {
    const res=await adminFetch(API_BASE+`/api/admin/appointments?${params}`);
    const appointments=await res.json();
    renderAdminAppointments(appointments);
    lista.dataset.cachedJson=JSON.stringify(appointments);
  } catch(e){lista.innerHTML=`<p class="vazio">${t("dashboard_error")}</p>`;}
}

function renderAdminAppointments(appointments) {
  const lista=document.getElementById("lista-appointments-admin");
  if(!appointments||appointments.length===0){lista.innerHTML=`<p class="vazio">${t("agenda_empty_for_date")}</p>`;return;}
  lista.innerHTML=appointments.map(a=>{
    const statusClass=`status-${a.status}`;
    const statusLabel=t(`status_${a.status}`);
    const serviceName=a.services?a.services.name:"";
    const barberName=a.barbers?a.barbers.name:"";
    return `
      <div class="ficha">
        <div class="ficha-numero">${a.time.slice(0,5)}<small>${formatDate(a.date)}</small></div>
        <div class="ficha-info">
          <strong>${esc(a.client_name)}</strong>
          <span>${esc(serviceName)} · ${esc(barberName)}</span>
          <div class="ficha-meta"><span>📞 ${esc(a.client_phone)}</span></div>
          <span class="status-tag ${statusClass}" style="margin-top:6px;">${statusLabel}</span>
        </div>
      </div>`;
  }).join("");
}

async function loadBarbers() {
  const res=await adminFetch(API_BASE+"/api/admin/barbers");
  renderBarbers(await res.json());
}

function renderBarbers(barbers) {
  const lista=document.getElementById("lista-barbers");
  if(!barbers||barbers.length===0){lista.innerHTML=`<p class="vazio">${t("agenda_empty_for_date")}</p>`;return;}
  lista.innerHTML=barbers.map(b=>{
    const sc=b.active?"status-completed":"status-cancelled";
    const sl=b.active?t("label_active"):t("btn_deactivate");
    return `
      <div class="list-row" id="barber-${b.id}">
        <div class="list-row-info">
          <strong>${esc(b.name)}</strong>
          <span>${esc(b.email)}${b.phone?" — "+esc(b.phone):""}</span>
          <span class="status-tag ${sc}" style="margin-top:6px;">${sl}</span>
        </div>
        <div class="list-row-actions">
          ${b.active
            ? `<button class="btn-icon del" title="${t("btn_deactivate")}" onclick="toggleBarberActive('${b.id}',false)"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><circle cx="12" cy="12" r="10"/><line x1="4.9" y1="4.9" x2="19.1" y2="19.1"/></svg></button>`
            : `<button class="btn-icon edit" title="${t("label_active")}" onclick="toggleBarberActive('${b.id}',true)"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><polyline points="20 6 9 17 4 12"/></svg></button>`
          }
        </div>
      </div>`;
  }).join("");
  lista.dataset.cachedJson=JSON.stringify(barbers);
}

async function createBarber() {
  const name=document.getElementById("new-barber-name").value.trim();
  const email=document.getElementById("new-barber-email").value.trim();
  const phone=document.getElementById("new-barber-phone").value.trim();
  const password=document.getElementById("new-barber-password").value;
  if(!name||!email||!password){showMsg("msg-new-barber",t("msg_fill_required"),"erro");return;}
  const payload={name,email,password}; if(phone) payload.phone=phone;
  const res=await adminFetch(API_BASE+"/api/admin/barbers",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
  if(res.ok){
    showMsg("msg-new-barber",`${t("btn_add_barber")} ✓`,"sucesso");
    ["new-barber-name","new-barber-email","new-barber-phone","new-barber-password"].forEach(id=>document.getElementById(id).value="");
    loadBarbers();
  } else {const err=await res.json();showMsg("msg-new-barber",err.detail||t("msg_booking_error"),"erro");}
}

async function toggleBarberActive(id,active) {
  const res=await adminFetch(API_BASE+`/api/admin/barbers/${id}`,{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({active})});
  if(res.ok) loadBarbers();
}

async function loadServices() {
  const res=await adminFetch(API_BASE+"/api/admin/services");
  renderServices(await res.json());
}

function renderServices(services) {
  const lista=document.getElementById("lista-services");
  if(!services||services.length===0){lista.innerHTML=`<p class="vazio">${t("agenda_empty_for_date")}</p>`;return;}
  lista.innerHTML=services.map(s=>{
    const sc=s.active?"status-completed":"status-cancelled";
    const sl=s.active?t("label_active"):t("btn_deactivate");
    return `
      <div class="list-row" id="service-${s.id}">
        <div class="list-row-info">
          <strong>${esc(s.name)}</strong>
          <span>${formatCurrency(s.price)} — ${s.duration_minutes} min</span>
          <span class="status-tag ${sc}" style="margin-top:6px;">${sl}</span>
        </div>
        <div class="list-row-actions">
          ${s.active
            ? `<button class="btn-icon del" title="${t("btn_deactivate")}" onclick="toggleServiceActive('${s.id}',false)"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><circle cx="12" cy="12" r="10"/><line x1="4.9" y1="4.9" x2="19.1" y2="19.1"/></svg></button>`
            : `<button class="btn-icon edit" title="${t("label_active")}" onclick="toggleServiceActive('${s.id}',true)"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><polyline points="20 6 9 17 4 12"/></svg></button>`
          }
        </div>
      </div>`;
  }).join("");
  lista.dataset.cachedJson=JSON.stringify(services);
}

async function createService() {
  const name=document.getElementById("new-service-name").value.trim();
  const price=parseFloat(document.getElementById("new-service-price").value);
  const duration_minutes=parseInt(document.getElementById("new-service-duration").value,10);
  if(!name||isNaN(price)||isNaN(duration_minutes)){showMsg("msg-new-service",t("msg_fill_required"),"erro");return;}
  const res=await adminFetch(API_BASE+"/api/admin/services",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({name,price,duration_minutes})});
  if(res.ok){
    showMsg("msg-new-service",`${t("btn_add_service")} ✓`,"sucesso");
    document.getElementById("new-service-name").value="";
    document.getElementById("new-service-price").value="";
    document.getElementById("new-service-duration").value="30";
    loadServices();
  } else {const err=await res.json();showMsg("msg-new-service",err.detail||t("msg_booking_error"),"erro");}
}

async function toggleServiceActive(id,active) {
  const res=await adminFetch(API_BASE+`/api/admin/services/${id}`,{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({active})});
  if(res.ok) loadServices();
}

document.addEventListener("langchange",()=>{
  if(CURRENT_ADMIN_TAB==="dashboard"&&LAST_DASHBOARD_DATA){
    renderDashboard(LAST_DASHBOARD_DATA.data,LAST_DASHBOARD_DATA.today,LAST_DASHBOARD_DATA.clients,LAST_DASHBOARD_DATA.peak);
  } else if(CURRENT_ADMIN_TAB==="appointments-admin"){
    const lista=document.getElementById("lista-appointments-admin");
    if(lista&&lista.dataset.cachedJson) renderAdminAppointments(JSON.parse(lista.dataset.cachedJson));
  } else if(CURRENT_ADMIN_TAB==="barbers"){
    const lista=document.getElementById("lista-barbers");
    if(lista&&lista.dataset.cachedJson) renderBarbers(JSON.parse(lista.dataset.cachedJson));
  } else if(CURRENT_ADMIN_TAB==="services"){
    const lista=document.getElementById("lista-services");
    if(lista&&lista.dataset.cachedJson) renderServices(JSON.parse(lista.dataset.cachedJson));
  }
});

document.addEventListener("DOMContentLoaded",()=>{
  if(getAdminKey()) enterAdminDashboard();
});
