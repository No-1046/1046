(function(){
  const canvas = document.getElementById('bgCanvas');
  const ctx = canvas.getContext('2d');

  const lines = [
    {color:[56,189,248], width:2, speed:0.3, amp:0.06},
    {color:[99,102,241], width:1.5, speed:0.18, amp:0.04},
    {color:[16,185,129], width:1.2, speed:0.12, amp:0.03}
  ];

  let series = lines.map(()=>Array.from({length:200},()=>Math.random()*0.5+0.25));
  let phases = lines.map(()=>Math.random()*Math.PI*2);

  function resize(){
    const dpr = Math.min(window.devicePixelRatio||1,2);
    canvas.width = innerWidth * dpr;
    canvas.height = innerHeight * dpr;
    ctx.setTransform(dpr,0,0,dpr,0,0);
  }
  window.addEventListener('resize', resize);
  resize();

  function drawBackground(){
    const grad = ctx.createLinearGradient(0,0,0,canvas.height);
    grad.addColorStop(0,"#020617");
    grad.addColorStop(1,"#0f172a");
    ctx.fillStyle = grad;
    ctx.globalAlpha = 0.3;
    ctx.fillRect(0,0,canvas.width,canvas.height);
    ctx.globalAlpha = 1;
  }

  function drawLine(data, cfg){
    const w = canvas.width / (window.devicePixelRatio||1);
    const h = canvas.height / (window.devicePixelRatio||1);
    const col = cfg.color;
    const layers = [
      {alpha:0.06,width:cfg.width*8},
      {alpha:0.12,width:cfg.width*4},
      {alpha:0.9,width:cfg.width}
    ];
    for(const l of layers){
      ctx.beginPath();
      data.forEach((v,i)=>{
        const x = (i/(data.length-1))*w;
        const y = h*(1-v);
        if(i===0) ctx.moveTo(x,y);
        else ctx.lineTo(x,y);
      });
      ctx.strokeStyle = `rgba(${col[0]},${col[1]},${col[2]},${l.alpha})`;
      ctx.lineWidth = l.width;
      ctx.stroke();
    }
  }

  function update(){
    for(let i=0;i<lines.length;i++){
      const cfg=lines[i];
      phases[i]+=0.02;
      const t=performance.now()/1000*cfg.speed+phases[i];
      const base=0.5+Math.sin(t)*cfg.amp;
      const noise=(Math.random()-0.5)*0.02;
      const newVal=Math.max(0.02,Math.min(0.98,base+noise));
      series[i].shift();
      series[i].push(newVal);
    }
  }

  function render(){
    ctx.clearRect(0,0,canvas.width,canvas.height);
    drawBackground();
    for(let i=lines.length-1;i>=0;i--){
      drawLine(series[i],lines[i]);
    }
  }

  function loop(){
    update();
    render();
    requestAnimationFrame(loop);
  }
  loop();
})();
