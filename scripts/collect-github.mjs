import fs from "node:fs/promises";
const config=JSON.parse(await fs.readFile("config/students.json","utf8"));
const headers={"Accept":"application/vnd.github+json","X-GitHub-Api-Version":"2022-11-28"};
if(process.env.GH_PAT)headers.Authorization=`Bearer ${process.env.GH_PAT}`;
const now=new Date();
const day=86400000;
const iso=d=>d.toISOString();
async function api(path){const r=await fetch(`https://api.github.com${path}`,{headers});if(!r.ok)throw new Error(`${path}: ${r.status}`);return r.json()}
function ago(date){const days=Math.floor((now-new Date(date))/day);return days<1?"오늘":days===1?"어제":`${days}일 전`}
function status(last){const days=(now-new Date(last))/day;return days<=3?"active":days<=7?"watch":"inactive"}
const output=[];
for(const student of config.students){
  try{
    const commits=await api(`/repos/${student.repo}/commits?author=${encodeURIComponent(student.github)}&since=${encodeURIComponent(iso(new Date(now-49*day)))}&per_page=100`);
    const dates=commits.map(c=>c.commit.author?.date||c.commit.committer?.date).filter(Boolean);
    const recent7=dates.filter(d=>now-new Date(d)<7*day);
    const activeDays=new Set(recent7.map(d=>d.slice(0,10))).size;
    const weekly=Array.from({length:7},(_,i)=>dates.filter(d=>{const age=(now-new Date(d))/day;return age>=(6-i)*7&&age<(7-i)*7}).length);
    output.push({...student,commits:recent7.length,activeDays,lastCommit:dates[0]?ago(dates[0]):"기록 없음",status:dates[0]?status(dates[0]):"inactive",weekly,recent:commits.slice(0,5).map(c=>({message:c.commit.message.split("\n")[0],time:ago(c.commit.author?.date||c.commit.committer?.date),sha:c.sha.slice(0,7)}))});
  }catch(error){console.error(`${student.name}: ${error.message}`);output.push({...student,commits:0,activeDays:0,lastCommit:"수집 실패",status:"inactive",weekly:[0,0,0,0,0,0,0],recent:[]})}
}
await fs.mkdir("data",{recursive:true});
await fs.writeFile("data/students.json",JSON.stringify({course:config.course,notionUrl:config.notionUrl,updatedAt:new Intl.DateTimeFormat("ko-KR",{dateStyle:"short",timeStyle:"short",timeZone:"Asia/Seoul"}).format(now),students:output},null,2)+"\n");
