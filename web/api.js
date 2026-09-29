const configured = String(window.ENSALAMENTO_CONFIG?.API_BASE || '').trim().replace(/\/$/,'');
const isLocal = ['localhost','127.0.0.1','[::1]'].includes(location.hostname);
export const API_BASE = configured || (isLocal ? location.origin : '');
export class ApiError extends Error {constructor(message,status,details){super(message);this.status=status;this.details=details;}}
let csrf='';
export const setCsrf=value=>{csrf=value || '';};
export async function request(path,{method='GET',body,signal}={}){
  if(!API_BASE)throw new ApiError('O serviço de dados ainda não foi configurado. Use o exemplo de consulta ou configure API_BASE no site.',0);
  const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),25000);
  try{
    const response=await fetch(`${API_BASE}${path}`,{method,credentials:'include',headers:{Accept:'application/json',...(body!==undefined?{'Content-Type':'application/json'}:{}),...(method!=='GET' && csrf?{'X-CSRF-Token':csrf}:{})},...(body!==undefined?{body:JSON.stringify(body)}:{}),signal:signal || controller.signal,cache:'no-store'});
    const data=await response.json().catch(()=>({message:'O serviço devolveu uma resposta inesperada. Tente atualizar a página.'}));
    if(!response.ok)throw new ApiError(data.message || data.error || 'Não foi possível concluir a operação.',response.status,data.details);
    if(data.csrf_token)setCsrf(data.csrf_token);
    return data;
  }catch(error){if(error instanceof ApiError)throw error;throw new ApiError(error.name==='AbortError'?'O serviço demorou para responder. Aguarde alguns segundos e tente novamente.':'Não foi possível conectar ao serviço. Confira sua conexão e tente atualizar.',0);}
  finally{clearTimeout(timer);}
}
