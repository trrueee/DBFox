import { useState, type MouseEvent } from "react";
import { Database, FileText, Search, Sparkles, Terminal, Table2, GitMerge, X, Plus, Send, Trash2, Play } from "lucide-react";
import "./App.css";

type T = { id: string; title: string; type: "ask" | "table" | "sql" | "multi" | "result"; table?: string; tables?: string[]; query?: string };
type M = { show: boolean; x: number; y: number; kind: "db" | "schema" | "table" | "multi"; target: string };
const mods = [
  ["账号模块", ["id_users", "id_organizations", "id_departments"]],
  ["内容模块", ["note_infos", "video_infos"]],
  ["互动模块", ["comment_infos", "like_infos", "favorite_infos"]],
  ["流量模块", ["video_watch_records"]],
  ["配置表", ["config_system", "config_dict"]],
] as const;
const rows: Record<string, string[][]> = {
  id_users: [["1", "10001", "张三", "zhangsan", "active"], ["2", "10001", "李四", "lisi", "active"], ["3", "10002", "王五", "wangwu", "inactive"]],
  comment_infos: [["101", "20001", "1", "这个系统界面不错", "active"], ["102", "20002", "2", "数据字典在哪里配置", "pending"]],
  video_infos: [["501", "智能问数新手引导", "03:45", "1240", "active"]],
};
const defaultRows = rows.id_users;
const sqlText = "SELECT\n  u.name, COUNT(c.id) AS comment_count\nFROM id_users u\nLEFT JOIN comment_infos c ON u.id = c.user_id\nGROUP BY u.id, u.name\nORDER BY comment_count DESC;";

export default function App() {
  const [tabs, setTabs] = useState<T[]>([{ id: "ask", title: "问数工作台", type: "ask" }]);
  const [active, setActive] = useState("ask");
  const [selected, setSelected] = useState<string[]>([]);
  const [ctx, setCtx] = useState<string[]>([]);
  const [ask, setAsk] = useState("帮我查最近 7 天新增用户数量趋势");
  const [menu, setMenu] = useState<M>({ show: false, x: 0, y: 0, kind: "table", target: "" });
  const cur = tabs.find(t => t.id === active) || tabs[0];
  const open = (t: T) => { setTabs(p => p.some(x => x.id === t.id) ? p : [...p, t]); setActive(t.id); };
  const openTable = (name: string) => { open({ id: "table:" + name, title: name, type: "table", table: name }); setSelected([name]); };
  const openSql = () => open({ id: "sql:" + Date.now(), title: "SQL 控制台", type: "sql" });
  const openResult = () => ask.trim() && open({ id: "result:" + Date.now(), title: "问数结果", type: "result", query: ask });
  const close = (e: MouseEvent, id: string) => { e.stopPropagation(); setTabs(p => p.filter(t => t.id !== id)); if (active === id) setActive("ask"); };
  const rc = (e: MouseEvent, kind: M["kind"], target: string) => { e.preventDefault(); e.stopPropagation(); setMenu({ show: true, x: e.clientX, y: e.clientY, kind: kind === "table" && selected.length > 1 && selected.includes(target) ? "multi" : kind, target }); };
  const choose = (e: MouseEvent, name: string) => e.ctrlKey || e.metaKey ? setSelected(p => p.includes(name) ? p.filter(x => x !== name) : [...p, name]) : openTable(name);
  const pane = () => cur.type === "ask" ? <Ask ask={ask} setAsk={setAsk} ctx={ctx} setCtx={setCtx} openResult={openResult} openTable={openTable} /> : cur.type === "table" ? <Table name={cur.table || "id_users"} openSql={openSql} /> : cur.type === "sql" ? <Sql /> : cur.type === "multi" ? <Multi tables={cur.tables || []} /> : <Result q={cur.query || ""} openSql={openSql} />;
  return <div className="app" onClick={() => setMenu(m => ({ ...m, show: false }))}>
    <header><b>数据库可视化 + 智能问数</b><nav><button className="on">工作台</button><button>数据库</button><button>智能问数</button></nav><span>A</span></header>
    <main><aside><h3>数据源</h3><div className="source" onContextMenu={e => rc(e, "db", "prod-mysql")}><Database size={18}/><b>prod-mysql</b><small>MySQL 8.0</small></div><label><Search size={14}/><input placeholder="搜索表或字段"/></label><div className="tree"><p onContextMenu={e=>rc(e,"schema","小红书数据")}><Database size={14}/>小红书数据</p>{mods.map(m=><section key={m[0]}><h4>{m[0]}</h4>{m[1].map(t=><button key={t} className={selected.includes(t)?"sel":""} draggable onDragStart={e=>e.dataTransfer.setData("text/plain",t)} onClick={e=>choose(e,t)} onContextMenu={e=>rc(e,"table",t)}><FileText size={13}/>{t}</button>)}</section>)}</div></aside><section className="work"><div className="tabs">{tabs.map(t=><button key={t.id} className={t.id===active?"on":""} onClick={()=>setActive(t.id)}>{t.type==="ask"?<Sparkles size={14}/>:t.type==="sql"?<Terminal size={14}/>:<Table2 size={14}/>}<span>{t.title}</span>{t.id!=="ask"&&<X size={12} onClick={e=>close(e,t.id)}/>}</button>)}<button onClick={openSql}><Plus size={14}/></button></div><div className="pane">{pane()}</div></section></main>
    {menu.show&&<Menu m={menu} selected={selected} openTable={openTable} openSql={openSql} openMulti={()=>open({id:"multi:"+Date.now(),title:`联合 Workspace (${selected.length})`,type:"multi",tables:selected})} addCtx={()=>setCtx(p=>p.includes(menu.target)?p:[...p,menu.target])}/>} </div>;
}
function Ask(p:{ask:string;setAsk:(s:string)=>void;ctx:string[];setCtx:(s:string[])=>void;openResult:()=>void;openTable:(s:string)=>void}){return <div className="ask"><h1>你好，开始你的<span>智能问数之旅</span></h1><p>左侧是数据源树，中间是 Workspace Tabs。表、SQL、问数结果都在中间打开。</p><div className="ctx" onDragOver={e=>e.preventDefault()} onDrop={e=>{const t=e.dataTransfer.getData("text/plain");t&&p.setCtx([...p.ctx,t])}}><GitMerge size={15}/>{p.ctx.length?p.ctx.map(t=><em key={t}>{t}</em>):"拖拽表到这里作为问数上下文"}</div><div className="askbox"><textarea value={p.ask} onChange={e=>p.setAsk(e.target.value)}/><button onClick={p.openResult}><Send size={18}/></button></div><div className="cards">{["分析近 7 天评论数据趋势","查询活跃用户 Top 10","统计本月新增笔记数量","检查异常数据"].map(x=><button key={x} onClick={()=>p.setAsk(x)}><Sparkles size={16}/><b>{x}</b><small>数据分析</small></button>)}</div><h3>最近访问</h3><div className="recent">{["id_users","comment_infos","video_infos","note_infos"].map(t=><button key={t} onClick={()=>p.openTable(t)}>{t}</button>)}</div></div>}
function Table({name,openSql}:{name:string;openSql:()=>void}){const r=rows[name]||defaultRows;return <div className="tablePage"><div className="obj"><small>prod-mysql / 小红书数据</small><h2>{name}</h2><button onClick={openSql}><Terminal size={14}/>SQL 查询</button></div><nav><button className="on">数据预览</button><button>字段结构</button><button>关系图</button><button>样例查询</button></nav><table><thead><tr>{["id","tenant_id","name/content","account","status"].map(c=><th key={c}>{c}</th>)}</tr></thead><tbody>{r.map((x,i)=><tr key={i}>{x.map(y=><td key={y}><Status v={y}/></td>)}</tr>)}</tbody></table></div>}
function Status({v}:{v:string}){return ["active","inactive","pending"].includes(v)?<mark className={v}>{v}</mark>:<>{v}</>}
function Sql(){return <div className="sql"><div><b>SQL Console</b><button><Play size={14}/>运行</button></div><pre>{sqlText}</pre><section>点击运行后在这里显示查询结果、消息日志和 AI 解释。</section></div>}
function Multi({tables}:{tables:string[]}){return <div className="multi"><h2>联合 Workspace</h2><p>已选择：{tables.join("，")}</p><button><GitMerge size={18}/>分析表关联拓扑</button><button><Sparkles size={18}/>联合趋势统计</button></div>}
function Result({q,openSql}:{q:string;openSql:()=>void}){return <div className="result"><h2>“{q}”</h2><article><b>关键结论</b><p>最近 7 天新增用户整体呈上升趋势，可以继续按组织、状态拆分分析。</p></article><article><b>生成的 SQL</b><pre>{sqlText}</pre><button onClick={openSql}>在 SQL 控制台打开</button></article></div>}
function Menu(p:{m:M;selected:string[];openTable:(s:string)=>void;openSql:()=>void;openMulti:()=>void;addCtx:()=>void}){return <div className="menu" style={{left:p.m.x,top:p.m.y}} onClick={e=>e.stopPropagation()}>{p.m.kind==="table"&&<><button onClick={()=>p.openTable(p.m.target)}><Table2 size={14}/>预览表数据</button><button onClick={p.openSql}><Terminal size={14}/>打开 SQL 控制台</button><button onClick={p.addCtx}><Sparkles size={14}/>作为问数上下文</button><hr/><button className="danger"><Trash2 size={14}/>删除表</button></>}{p.m.kind==="multi"&&<button onClick={p.openMulti}><GitMerge size={14}/>作为联合 Workspace 打开</button>}{p.m.kind!=="table"&&p.m.kind!=="multi"&&<button onClick={p.openSql}><Terminal size={14}/>打开 SQL 控制台</button>}</div>}
