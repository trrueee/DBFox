async (page) => {
  await page.setContent('<main id="probe"></main>');
  await page.addScriptTag({ url: 'https://unpkg.com/konva@10.3.3/konva.min.js' });
  const result = await page.evaluate(async () => {
    const samples = ['风从海面吹过，我们终于抵达灯塔。\n下一幕：重逢。', 'Long English dialogue without breaking layout at narrow widths.', '朋友 👩🏽‍🚀 与家人 👨‍👩‍👧‍👦 é'];
    const records = [];
    for (const text of samples) {
      const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
      svg.setAttribute('xmlns', 'http://www.w3.org/2000/svg'); svg.setAttribute('width', '240'); svg.setAttribute('height', '180');
      const fo = document.createElementNS(svg.namespaceURI, 'foreignObject'); fo.setAttribute('width', '220'); fo.setAttribute('height', '160');
      const div = document.createElementNS('http://www.w3.org/1999/xhtml', 'div');
      div.setAttribute('style', 'font:20px/1.4 sans-serif;white-space:pre-wrap;overflow-wrap:anywhere;width:200px;color:#111;background:#fff;padding:10px');
      div.textContent = text; fo.append(div); svg.append(fo); document.getElementById('probe').append(svg);
      const standalone = new XMLSerializer().serializeToString(svg);
      const img = new Image(); img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(standalone); await img.decode();
      const canvas = document.createElement('canvas'); canvas.width=240;canvas.height=180;canvas.getContext('2d').drawImage(img,0,0);
      const pixels=canvas.getContext('2d').getImageData(0,0,240,180).data;
      const container=document.createElement('div');document.body.append(container);
      const stage=new Konva.Stage({container,width:240,height:180}); const layer=new Konva.Layer();stage.add(layer);
      const ktext=new Konva.Text({text,width:220,fontFamily:'sans-serif',fontSize:20,padding:10,wrap:'word',lineHeight:1.4});layer.add(ktext);layer.draw();
      records.push({text,htmlHeight:div.getBoundingClientRect().height,htmlWidth:div.scrollWidth,svgReopenInk:pixels.filter((v,i)=>i%4===3 && v>0).length,svgPngBytes:canvas.toDataURL().length,konvaHeight:ktext.height(),konvaPngBytes:stage.toDataURL().length});
      stage.destroy();container.remove();
    }
    return {browser:navigator.userAgent,konvaVersion:Konva.version,records};
  });
  await page.screenshot({path:'comic-renderer-probe.png'});
  return result;
}
