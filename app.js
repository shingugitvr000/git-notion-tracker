const labels={active:"정상",watch:"확인 필요",inactive:"미활동"};
const state={data:null,github:"",selectedRepo:"",copyMessage:""};
const $=(q)=>document.querySelector(q);
const esc=(v)=>String(v??"").replace(/[&<>'"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[c]));
const githubParam=()=>new URLSearchParams(window.location.search).get("github")?.trim()??"";
const normalizeGithub=(value)=>value.trim().replace(/^@/,"").toLowerCase();
const allowedTypes=["Feat","Fix","Refactor","Docs","Chore","Test","Design","Implement"];
const recommendedTypes=["Feat","Fix","Refactor","Docs","Chore"];
const typeDescriptions={
  Feat:"새 기능, 시스템, 콘텐츠 추가",
  Fix:"버그 수정, 예외 처리, 충돌 해결",
  Refactor:"동작 변화 없이 구조 개선",
  Docs:"문서, 가이드, 설명 보강",
  Chore:"설정, 정리, 리소스, 빌드 작업"
};

async function load(){
  try{
    const response=await fetch(`data/students.json?v=${Date.now()}`);
    if(!response.ok) throw new Error("data load failed");
    state.data=await response.json();
    state.github=normalizeGithub(githubParam());
    $("#courseTitle").textContent=state.data.course;
    $("#updatedAt").textContent=`마지막 동기화 · ${state.data.updatedAt}`;
    bind();
    render();
  }catch(error){
    $("#dashboard").innerHTML='<div class="error">데이터를 불러오지 못했습니다. GitHub Pages 배포 상태와 data/students.json을 확인하세요.</div>';
  }
}

function bind(){
  window.addEventListener("popstate",()=>{
    state.github=normalizeGithub(githubParam());
    state.selectedRepo="";
    render();
  });
  $("#dashboard").addEventListener("submit",event=>{
    const form=event.target.closest("#githubLookupForm");
    if(!form) return;
    event.preventDefault();
    const input=form.querySelector('input[name="github"]');
    const github=normalizeGithub(input?.value??"");
    state.github=github;
    state.selectedRepo="";
    const nextUrl=github?`${window.location.pathname}?github=${encodeURIComponent(github)}`:window.location.pathname;
    window.history.pushState({github},"",nextUrl);
    render();
  });
  $("#dashboard").addEventListener("click",event=>{
    const repoButton=event.target.closest("[data-repo]");
    if(repoButton){
      state.selectedRepo=repoButton.dataset.repo;
      render();
      return;
    }
    if(event.target.closest("[data-copy-embed]")){
      copyEmbedLink();
      return;
    }
    if(event.target.closest("[data-reset-github]")){
      state.github="";
      state.selectedRepo="";
      state.copyMessage="";
      window.history.pushState({github:""},"",window.location.pathname);
      render();
    }
  });
}

function matchedStudents(){
  const github=normalizeGithub(state.github);
  if(!github) return [];
  return state.data.students.filter(student=>normalizeGithub(student.github)===github);
}

function selectedStudent(students){
  if(!students.length) return null;
  const fallback=students[0].repo;
  if(!students.some(student=>student.repo===state.selectedRepo)) state.selectedRepo=fallback;
  return students.find(student=>student.repo===state.selectedRepo)??students[0];
}

function render(){
  const students=matchedStudents();
  if(!state.github){
    $("#dashboard").innerHTML=renderLookup();
    return;
  }
  if(!students.length){
    $("#dashboard").innerHTML=renderLookup(`GitHub ID "${esc(state.github)}"에 연결된 프로젝트를 찾지 못했습니다.`);
    return;
  }
  renderDashboard(students);
}

function renderLookup(message=""){
  return `
    <section class="lookup-card">
      <p class="lookup-eyebrow">개인별 프로젝트 조회</p>
      <h1>Github ID를 입력해서 내 프로젝트 진행 사항을 확인 하세요.</h1>
      <form id="githubLookupForm" class="lookup-form">
        <label class="lookup-input">
          <span>GitHub ID</span>
          <input name="github" placeholder="" autocomplete="off" value="${esc(state.github)}">
        </label>
        <button type="submit">프로젝트 보기</button>
      </form>
      ${message?`<p class="lookup-message error">${message}</p>`:""}
    </section>`;
}

function getSemesterInfo(date=new Date()){
  const year=date.getFullYear();
  const month=date.getMonth();
  const semester=month<6?1:2;
  return {
    label:`${year}학년도 ${semester}학기`,
    range:semester===1?`${year}.01.01 ~ ${year}.06.30`:`${year}.07.01 ~ ${year}.12.31`
  };
}

function analyzeCommitMessages(commits){
  const report={total:commits.length,valid:0,ruleCompliant:0,recommended:0,warnings:[],typeCounts:{}};
  commits.forEach(commit=>{
    const message=String(commit.message??"").trim();
    const match=message.match(/^\[(\w+)\]\s+(.+)$/);
    if(!match){
      report.warnings.push({message,reason:"형식이 `[Feat] 내용` 규칙과 다릅니다."});
      return;
    }
    const [,type,title]=match;
    const normalizedType=type[0]?.toUpperCase()+type.slice(1).toLowerCase();
    if(!allowedTypes.includes(normalizedType)){
      report.warnings.push({message,reason:`타입 "${normalizedType}"은 권장 목록에 없습니다.`});
      return;
    }
    report.typeCounts[normalizedType]=(report.typeCounts[normalizedType]??0)+1;
    report.valid+=1;
    if(title.trim().length>=6) report.ruleCompliant+=1;
    else report.warnings.push({message,reason:"설명이 너무 짧아 작업 내용이 잘 드러나지 않습니다."});
    if(recommendedTypes.includes(normalizedType)) report.recommended+=1;
    else report.warnings.push({message,reason:`"${normalizedType}" 대신 핵심 타입(Feat/Fix/Refactor/Docs/Chore) 사용을 권장합니다.`});
  });
  return report;
}

function activityInsights(student,quality){
  const weekly=student.weekly??[];
  const activeWeeks=weekly.filter(value=>value>0).length;
  const peakValue=Math.max(...weekly,0);
  const peakIndex=weekly.indexOf(peakValue);
  const recentTotal=weekly.slice(-3).reduce((sum,value)=>sum+value,0);
  const previousTotal=weekly.slice(-6,-3).reduce((sum,value)=>sum+value,0);
  const trend=recentTotal>previousTotal?"상승":recentTotal<previousTotal?"감소":"유지";
  const topType=Object.entries(quality.typeCounts).sort((a,b)=>b[1]-a[1])[0];
  return [
    {label:"활동 밀도",value:`${activeWeeks}/${weekly.length}주`,detail:activeWeeks?`최근 ${weekly.length}주 중 실제 커밋이 있었던 주차입니다.`:"최근 주차 활동 기록이 없습니다."},
    {label:"가장 활발한 주",value:peakValue?`${peakIndex+1}주차`:"없음",detail:peakValue?`${peakValue}회의 커밋으로 가장 활발했습니다.`:"집계된 커밋이 없습니다."},
    {label:"최근 흐름",value:trend,detail:`최근 3주 ${recentTotal}회, 이전 3주 ${previousTotal}회 기준입니다.`},
    {label:"작업 성격",value:topType?`${topType[0]} 중심 (${topType[1]}건)`:"분석 데이터 없음",detail:`최근 메시지 기준으로 ${topType?typeDescriptions[topType[0]]:"추가 분석이 어렵습니다."}`}
  ];
}

function renderInsightList(items){
  return `<div class="insight-list">${items.map(item=>`<article class="insight-item"><span class="insight-label">${esc(item.label)}</span><strong>${esc(item.value)}</strong><p>${esc(item.detail)}</p></article>`).join("")}</div>`;
}

function renderWeeklyBars(weekly){
  const max=Math.max(...weekly,1);
  return `<div class="bar-chart" aria-label="최근 7주 활동">${weekly.map((value,index)=>`<div class="bar-item ${value===max&&value>0?"peak":""}"><em>${value}</em><i style="height:${Math.max(12,Math.round(value/max*100))}%"></i><small>${index+1}주</small></div>`).join("")}</div>`;
}

function renderTypeGuide(){
  return `<ul class="guide-types">${recommendedTypes.map(type=>`<li><strong class="type-token">[${type}]</strong><p>${esc(typeDescriptions[type])}</p></li>`).join("")}<li class="guide-update"><strong class="type-token">[Update]</strong><p>너무 넓은 표현이라 가능하면 Feat, Fix, Refactor, Chore 중 하나로 구체화하세요.</p></li></ul>`;
}

function renderQualityList(items){
  if(!items.length) return '<p class="empty small">최근 커밋 기준으로 규칙 위반이 보이지 않습니다.</p>';
  return `<ul class="quality-list">${items.map(item=>`<li><strong>${esc(item.message)}</strong><p>${esc(item.reason)}</p></li>`).join("")}</ul>`;
}

async function copyEmbedLink(){
  try{
    if(navigator.clipboard?.writeText){
      await navigator.clipboard.writeText(window.location.href);
      state.copyMessage="노션에 복사해서 임베드 하세요.";
    }else{
      throw new Error("clipboard unavailable");
    }
  }catch(error){
    state.copyMessage="클립보드 복사에 실패했습니다. 브라우저 권한을 확인하세요.";
  }
  render();
}

function renderDashboard(students){
  const s=selectedStudent(students); if(!s) return;
  const semester=getSemesterInfo();
  const quality=analyzeCommitMessages(s.recent);
  const total=s.weekly.reduce((a,b)=>a+b,0);
  const commits=s.recent.length?s.recent.map(c=>`<div class="commit"><span>⌘</span><div><strong>${esc(c.message)}</strong><p><code>${esc(c.sha)}</code> · ${esc(s.github)}</p></div><time>${esc(c.time)}</time></div>`).join(""):'<p class="empty">최근 커밋이 없습니다.</p>';
  const repoTabs=students.length>1?`<nav class="repo-switcher" aria-label="저장소 전환">${students.map(student=>`<button class="repo-tab ${student.repo===s.repo?"current":""}" data-repo="${esc(student.repo)}">${esc(student.repo)}</button>`).join("")}</nav>`:"";
  const copyNotice=state.copyMessage?`<p class="copy-feedback">${esc(state.copyMessage)}</p>`:"";
  const qualityRate=quality.total?Math.round(quality.ruleCompliant/quality.total*100):0;
  const insights=activityInsights(s,quality);
  $("#dashboard").innerHTML=`
    <div class="dashboard-tools"><button class="ghost-button" type="button" data-copy-embed>노션 임베드 복사</button><button class="ghost-button" type="button" data-reset-github>다른 GitHub ID 입력</button></div>
    ${copyNotice}
    <div class="student-head"><div><p>${esc(semester.label)}</p><h1>${esc(s.name)}<small>${esc(s.id)}</small></h1><a href="https://github.com/${esc(s.github)}" target="_blank" rel="noopener">github.com/${esc(s.github)} ↗</a><div class="semester-range">집계 기간 · ${esc(semester.range)}</div></div><span class="chip ${esc(s.status)}"><i></i>${esc(labels[s.status])}</span></div>
    ${repoTabs}
    <div class="metrics"><article><span>학기 활동 커밋</span><strong>${total}<small>회</small></strong><p>${esc(semester.label)} 집계 기준</p></article><article><span>유효 커밋</span><strong>${quality.valid}<small>/ ${quality.total||0}</small></strong><p>최근 커밋 메시지 형식 점검</p></article><article><span>규칙 준수율</span><strong class="time">${qualityRate}<small>%</small></strong><p>${quality.recommended}개가 핵심 타입 규칙을 따릅니다</p></article></div>
    <div class="content-grid">
      <article class="card activity-card">
        <div class="card-head"><div><h2>최근 활동 흐름</h2><p>커밋 수를 해석한 프로젝트 진행 신호</p></div><span>총 ${total}회</span></div>
        <div class="activity-chart-card"><div class="activity-caption"><strong>주차별 활동</strong><p>최근 7주 커밋 수를 막대그래프로 보여줍니다.</p></div>${renderWeeklyBars(s.weekly)}</div>
        ${renderInsightList(insights)}
      </article>
      <article class="card guide guide-card"><div class="card-head"><div><h2>커밋 규칙 가이드</h2><p>학생이 바로 따라 쓸 수 있는 타입 안내</p></div></div>${renderTypeGuide()}<ol><li><span>01</span><div><strong>형식 통일</strong><p>[Feat] 플레이어 점프 판정 수정처럼 타입 뒤에 작업 내용을 적습니다.</p></div></li><li><span>02</span><div><strong>Update 지양</strong><p>무엇을 바꿨는지 보이도록 Feat, Fix, Refactor, Chore로 구체화합니다.</p></div></li><li><span>03</span><div><strong>짧은 제목 피하기</strong><p>수정, 테스트, 작업중 같은 모호한 표현은 평가 근거가 약합니다.</p></div></li></ol></article>
    </div>
    <div class="content-grid secondary"><article class="card quality"><div class="card-head"><div><h2>유효 커밋 점검</h2><p>최근 메시지 기준 자동 판정</p></div><span>${qualityRate}%</span></div>${renderQualityList(quality.warnings.slice(0,4))}</article><article class="card semester"><div class="card-head"><div><h2>학기 집계 기준</h2><p>방학 중 커밋도 동일하게 포함합니다</p></div></div><ul class="quality-list static"><li><strong>1학기</strong><p>매년 1월 1일 ~ 6월 30일</p></li><li><strong>2학기</strong><p>매년 7월 1일 ~ 12월 31일</p></li><li><strong>집계 방식</strong><p>해당 기간 안의 모든 커밋을 학기 활동으로 반영</p></li></ul></article></div>
    <article class="card commits"><div class="card-head"><div><h2>최근 커밋</h2><p>${esc(s.repo)}</p></div><a href="https://github.com/${esc(s.repo)}/commits" target="_blank" rel="noopener">전체 보기 ↗</a></div><div>${commits}</div></article>`;
}

load();
