document.addEventListener('DOMContentLoaded',()=>{
  const csrfToken=document.querySelector('meta[name="csrf-token"]')?.content||'';
  document.querySelectorAll('form').forEach(form=>{
    if((form.method||'get').toLowerCase()!=='post'||form.querySelector('input[name="csrf_token"]'))return;
    const input=document.createElement('input');input.type='hidden';input.name='csrf_token';input.value=csrfToken;form.appendChild(input);
  });

  const hospital=document.querySelector('#hospital');
  const department=document.querySelector('#department');
  if(hospital&&department){
    const options=[...department.querySelectorAll('option[data-hospital]')];
    const filter=()=>{options.forEach(o=>{o.hidden=o.dataset.hospital!==hospital.value});if(department.selectedOptions[0]?.hidden)department.value=''};
    hospital.addEventListener('change',filter);filter();
  }

  document.querySelectorAll('[data-password-toggle]').forEach(button=>button.addEventListener('click',()=>{
    const input=document.querySelector(button.dataset.passwordToggle);
    if(!input)return;
    input.type=input.type==='password'?'text':'password';
    button.innerHTML=`<i class="bi ${input.type==='password'?'bi-eye':'bi-eye-slash'}"></i>`;
  }));

  let pendingForm=null;
  const confirmElement=document.querySelector('#confirmModal');
  const confirmMessage=document.querySelector('#confirmModalMessage');
  const confirmAction=document.querySelector('#confirmModalAction');
  const confirmModal=confirmElement?new bootstrap.Modal(confirmElement):null;
  document.querySelectorAll('form[data-confirm]').forEach(form=>form.addEventListener('submit',event=>{
    if(form.dataset.confirmed)return;
    event.preventDefault();pendingForm=form;
    if(confirmMessage)confirmMessage.textContent=form.dataset.confirm||'Are you sure you want to continue?';
    confirmModal?.show();
  }));
  confirmAction?.addEventListener('click',()=>{if(!pendingForm)return;pendingForm.dataset.confirmed='true';confirmModal?.hide();pendingForm.requestSubmit()});

  document.querySelectorAll('form').forEach(form=>form.addEventListener('submit',()=>{
    const button=form.querySelector('button[type="submit"],button:not([type])');
    if(!button||form.dataset.confirm&&!form.dataset.confirmed)return;
    button.disabled=true;button.dataset.originalText=button.innerHTML;button.innerHTML='<span class="spinner-border spinner-border-sm me-2"></span>Working…';
  }));

  document.querySelectorAll('[data-table-filter]').forEach(input=>input.addEventListener('input',()=>{
    const table=document.querySelector(input.dataset.tableFilter);if(!table)return;
    const query=input.value.toLowerCase();
    table.querySelectorAll('tbody tr').forEach(row=>row.hidden=!row.textContent.toLowerCase().includes(query));
  }));

  document.querySelectorAll('[data-notification-read]').forEach(button=>button.addEventListener('click',async()=>{
    button.disabled=true;const original=button.textContent;button.textContent='Updating…';
    try{
      const response=await fetch(`/api/patient/notifications/${button.dataset.notificationRead}/read`,{method:'POST',credentials:'same-origin',headers:{'X-CSRF-Token':csrfToken}});
      if(!response.ok)throw new Error('Request failed');
      const card=button.closest('.notification-card');card?.classList.remove('unread');
      const badge=card?.querySelector('.notification-status');if(badge){badge.className='badge status-read notification-status';badge.textContent='READ'}
      button.remove();
    }catch(error){button.disabled=false;button.textContent=original;}
  }));
});
