async(page)=>{
const m=await page.getByRole('region',{name:'Animation Studio',exact:true}).evaluate(el=>({viewport:innerWidth,document:document.documentElement.scrollWidth,width:el.getBoundingClientRect().width,client:el.clientWidth,scroll:el.scrollWidth,descendants:el.querySelectorAll('*').length,rows:el.querySelectorAll('tbody tr').length,version:el.querySelector('[role=status]')?.textContent}));
if(m.document>m.viewport||m.scroll>m.client+1||m.width<300)throw Error(JSON.stringify(m));return m;
}