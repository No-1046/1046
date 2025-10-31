(function(){
  const canvas = document.getElementById('bgCanvas');
  const ctx = canvas.getContext('2d');

  const lines = [
    {color:[56,189,248], width:2, speed:0.1, amp:0.1},
    {color:[99,102,241], width:1.5, speed:0.2, amp:0.11},
    {color:[16,185,129], width:1.2, speed:0.3, amp:0.12}
  ];

// --- 変更ここから ---

  const dataLength = 200; // データ長（元のコードの 200 と合わせる）
  
  // 1. 先に「位相（波の開始位置）」を決める
  let phases = lines.map(()=>Math.random()*Math.PI*2);

  // 2. 「位相」と「設定」を使って、最初からサイン波のデータで配列を埋める
  let series = lines.map((cfg, i) => { // (cfg: 設定, i: インデックス)
    
    const phase = phases[i]; // このラインの初期位相
    const amp = cfg.amp;     // このラインの振幅
    
    // update関数の `phases[i]+=0.02;` というロジックを使い、
    // 過去のデータを逆算して配列（dataLength個）を作る
    const phaseStep = 0.02; 

    return Array.from({ length: dataLength }, (v, j) => {
      // j は 0 (左端/最古) から 199 (右端/最新) まで
      
      // (j - (dataLength - 1)) は -199 から 0 までの値になる
      // これに位相のステップを掛けて、j=199 の時に位相が phase になるよう調整する
      const t = phase + (j - (dataLength - 1)) * phaseStep;
      
      // update関数と同様の計算 (ノイズを除く)
      const base = 0.5 + Math.sin(t) * amp;
      const noise = (Math.random() - 0.5) * 0.1; 
      const newVal = base + noise;

      // 0.02〜0.98の範囲に収める
      return Math.max(0.02, Math.min(0.98, newVal));
    });
  });

  // --- 変更ここまで ---
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
      const noise=(Math.random()-0.5)*0.1;
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




  let lastUpdateTime = 0;
  // ▼▼▼ この数値を大きくすると、スクロールが「遅く」なります ▼▼▼
  const updateInterval = 50; // (ミリ秒) 50ms = 1秒間に20回 update
  // ▲▲▲ (例: 100にすると1秒間に10回、16.6だと約60回) ▲▲▲

  function loop(currentTime){
    requestAnimationFrame(loop); // 次のフレームを予約

    // render() は毎回呼び出し、描画は滑らかに保つ
    render();

    // 経過時間を計算
    const deltaTime = currentTime - lastUpdateTime;

    // 設定した updateInterval (50ms) 以上が経過した場合のみ
    if (deltaTime > updateInterval) {
      lastUpdateTime = currentTime - (deltaTime % updateInterval);
      
      // update() を実行する
      update(); 
    }
  }

  // ループを開始
  lastUpdateTime = performance.now();
  loop(lastUpdateTime);
})();