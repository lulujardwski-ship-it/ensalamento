export const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const paths = {
  calendar:'<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M16 3v4M8 3v4M3 11h18M8 15h2M14 15h2"/>',
  clock:'<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  pin:'<path d="M20 10c0 6-8 12-8 12S4 16 4 10a8 8 0 1 1 16 0Z"/><circle cx="12" cy="10" r="2.5"/>',
  search:'<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
  grid:'<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
  building:'<path d="M3 21h18M5 21V7l7-4 7 4v14M9 21v-5h6v5M9 8h1m4 0h1m-6 4h1m4 0h1"/>',
  book:'<path d="M12 5C8 2 4 3 2 4v15c4-2 7-1 10 1 3-2 6-3 10-1V4c-2-1-6-2-10 1Zm0 0v15"/>',
  users:'<circle cx="9" cy="8" r="3"/><path d="M3 20v-2a6 6 0 0 1 12 0v2M16 5a3 3 0 0 1 0 6M18 14a5 5 0 0 1 3 4v2"/>',
  arrow:'<path d="M4 12h16m-6-6 6 6-6 6"/>',
  chevron:'<path d="m9 5 7 7-7 7"/>',
  check:'<path d="m5 12 4 4L19 6"/>',
  shield:'<path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6l8-3Z"/><path d="m8 12 3 3 5-6"/>',
  info:'<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7v1"/>',
  alert:'<path d="m12 3 10 18H2L12 3Z"/><path d="M12 9v5M12 17v1"/>',
  refresh:'<path d="M20 7v5h-5M4 17v-5h5M6 7a7 7 0 0 1 12-2l2 3M4 16l2 3a7 7 0 0 0 12-2"/>',
  logout:'<path d="M10 4H4v16h6m4-12 4 4-4 4m-5-4h12"/>',
  menu:'<path d="M4 6h16M4 12h16M4 18h16"/>',
  close:'<path d="m6 6 12 12M18 6 6 18"/>',
  plus:'<path d="M12 4v16M4 12h16"/>',
  edit:'<path d="m15 4 5 5M4 20l5-1L21 7l-4-4L5 15l-1 5Z"/>',
  download:'<path d="M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5"/>',
  upload:'<path d="M12 16V4m-5 5 5-5 5 5M4 16v5h16v-5"/>',
  history:'<path d="M3 11a9 9 0 1 1 2 7M3 4v7h7M12 7v5l4 2"/>',
  layers:'<path d="m12 3 10 6-10 6L2 9l10-6ZM2 13l10 6 10-6M2 17l10 6 10-6"/>',
  wand:'<path d="m4 20 12-12 4 4L8 24M14 10l4 4M6 3v4M4 5h4M18 2v3M20 4h-4M3 12v3M1 14h4"/>',
  lock:'<rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V6a4 4 0 0 1 8 0v4M12 14v3"/>',
  accessibility:'<circle cx="12" cy="4" r="2"/><path d="m4 8 8 2 8-2M12 10v5m0 0-5 7m5-7 5 7"/>',
  chart:'<path d="M4 3v18h17M8 17v-5M13 17V8M18 17V5"/>',
  external:'<path d="M14 3h7v7m0-7L10 14M11 3H3v18h18v-8"/>',
};
export const icon = name => `<svg class="icon" viewBox="0 0 24 24" aria-hidden="true">${paths[name] || paths.info}</svg>`;
export const button = (label, action, variant='secondary', attrs='') => `<button type="button" class="btn ${variant}" data-action="${action}" ${attrs}>${label}</button>`;
export const empty = (title,text,extra='') => `<div class="empty">${icon('calendar')}<h3>${esc(title)}</h3><p class="muted">${esc(text)}</p>${extra}</div>`;
export const notice = (text,type='') => `<div class="notice ${type}">${icon(type==='error'?'alert':'info')}<p>${esc(text)}</p></div>`;
export const roles = {admin:'Administrador',coordinator:'Coordenador',teacher:'Professor',student:'Aluno'};
export const statuses = {active:'Ativa',inactive:'Inativa',maintenance:'Manutenção',draft:'Rascunho',submitted:'Enviada',in_review:'Em revisão',approved:'Aprovada',cancelled:'Cancelada',closed:'Encerrada',published:'Publicada',archived:'Arquivada',automatic:'Automática',manual:'Manual'};
export function badge(status){return `<span class="pill ${['active','approved','published'].includes(status)?'good':['in_review','maintenance'].includes(status)?'warn':['cancelled','inactive'].includes(status)?'bad':''}">${esc(statuses[status] || status || 'Rascunho')}</span>`;}
export const weekdays=['Segunda-feira','Terça-feira','Quarta-feira','Quinta-feira','Sexta-feira','Sábado','Domingo'];
export function dateLabel(date,options={day:'2-digit',month:'long'}){if(!date)return '—';const value=date.length===10?`${date}T12:00:00`:date;const d=new Date(value);return Number.isNaN(d.getTime())?'—':new Intl.DateTimeFormat('pt-BR',options).format(d);}
export function dateTime(value){if(!value)return '—';try{return new Intl.DateTimeFormat('pt-BR',{dateStyle:'short',timeStyle:'short',timeZone:window.ENSALAMENTO_CONFIG?.TIMEZONE || 'America/Sao_Paulo'}).format(new Date(value));}catch{return '—';}}
export function localDate(){return new Intl.DateTimeFormat('en-CA',{timeZone:window.ENSALAMENTO_CONFIG?.TIMEZONE || 'America/Sao_Paulo',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());}
export function currentMinutes(){const v=new Intl.DateTimeFormat('en-GB',{timeZone:window.ENSALAMENTO_CONFIG?.TIMEZONE || 'America/Sao_Paulo',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).format(new Date());return minutes(v);}
export const minutes=s=>{const [h,m]=String(s||'00:00').split(':').map(Number);return h*60+m;};
export const weekdayOf=date=>(new Date(`${date}T12:00:00`).getDay()+6)%7;
export function addDays(date,n){const d=new Date(`${date}T12:00:00`);d.setDate(d.getDate()+n);return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;}
export const list=v=>Array.isArray(v)?v:String(v || '').split(';').map(x=>x.trim()).filter(Boolean);
export function toast(message,error=false){const node=document.querySelector('#toast');node.textContent=message;node.className=`toast visible ${error?'error':''}`;clearTimeout(toast.timer);toast.timer=setTimeout(()=>node.classList.remove('visible'),6000);}
export function openModal(title,body){const modal=document.querySelector('#modal');modal.innerHTML=`<div class="modal-header"><h2 id="modal-title">${esc(title)}</h2><button class="modal-close" data-action="close-modal" aria-label="Fechar janela">${icon('close')}</button></div><div class="modal-body">${body}</div>`;modal.showModal();return modal;}
export function closeModal(){document.querySelector('#modal').close();}
export function download(name,content,type='text/plain;charset=utf-8'){const url=URL.createObjectURL(new Blob([content],{type}));const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
export function buildingArt(label='Referência visual do prédio'){return `<svg class="building-art" viewBox="0 0 470 360" role="img" aria-label="${esc(label)}"><path d="m34 272 220-113 184 93-219 111Z" fill="#cbd9bd"/><path d="m104 141 120-65 147 75-120 66Z" fill="#f4f3dd"/><path d="M104 141v140l147 76V217Z" fill="#8fa88b"/><path d="M251 217v140l120-65V151Z" fill="#4d7562"/><path d="m92 132 134-73 158 82-133 73Z" fill="#e9ead4"/><path d="m92 132 159 82v12L92 144Z" fill="#bec9ac"/><path d="m251 214 133-73v12l-133 73Z" fill="#799479"/><g fill="#d8e5c9"><path d="m124 170 22 11v26l-22-11ZM163 190l22 12v26l-22-12ZM203 211l23 12v26l-23-12ZM124 220l22 11v26l-22-11ZM163 240l22 12v26l-22-12Z"/></g><g fill="#a8c0a0"><path d="m272 223 24-13v25l-24 13ZM314 201l24-13v25l-24 13ZM272 267l24-13v25l-24 13ZM314 245l24-13v25l-24 13Z"/></g><path d="m207 279 25 13v55l-25-13Z" fill="#2e5345"/><path d="m212 335 26 13 15-8-26-13Z" fill="#e8e8d1"/><path d="m206 342 32 16 22-12-32-16Z" fill="#bac9ad"/><g fill="#678860"><ellipse cx="79" cy="266" rx="27" ry="14"/><path d="M63 259V207h29v52Z"/><ellipse cx="77" cy="207" rx="29" ry="40"/></g><path d="M77 240v44" stroke="#547553" stroke-width="5"/><g fill="#88a47a"><ellipse cx="399" cy="293" rx="25" ry="12"/><ellipse cx="399" cy="244" rx="25" ry="35"/></g><path d="M399 266v34" stroke="#547553" stroke-width="5"/><path d="m48 304 88 43m236-30 57-29" stroke="#b4c7a5" stroke-width="3" stroke-linecap="round"/></svg>`;}
export function roomMap(room,building){return `<div class="room-map">${buildingArt(`${building?.name || 'Prédio'}: ilustração esquemática, sem escala`)}<small>Referência esquemática, sem escala. Use a localização textual para chegar.</small></div>`;}
