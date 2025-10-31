// main.js - 株価予測システム メインJavaScript

console.log('main.js loaded!'); // 読み込み確認用

// === スクロールでヘッダーを表示/非表示にするスクリプト ===
const header = document.getElementById('page-header');
const scrollIndicator = document.getElementById('scroll-indicator');
let lastScrollTop = 0;

window.addEventListener('scroll', () => {
    let scrollTop = window.pageYOffset || document.documentElement.scrollTop;
    if (scrollTop > 100) {
        if (scrollTop > lastScrollTop) {
            header.classList.remove('header-visible');
        } else {
            header.classList.add('header-visible');
        }
        scrollIndicator.classList.add('scroll-hidden');
    } else {
        header.classList.remove('header-visible');
        scrollIndicator.classList.remove('scroll-hidden');
    }
    lastScrollTop = scrollTop <= 0 ? 0 : scrollTop;
}, false);


// === オープニングビデオが終了したらロックを解除するスクリプト ===
const openingVideo = document.getElementById('opening-video');
const heroSection = document.querySelector('.hero');
const bodyElement = document.body;

function unlockPage() {
    
    console.log('unlockPage called'); // デバッグ用
    
    // bodyのスクロール禁止を解除
    bodyElement.classList.remove('no-scroll');
    
    // すべてのoverflowを明示的に解除
    document.documentElement.style.overflow = 'visible';
    document.documentElement.style.overflowX = 'hidden';
    document.documentElement.style.overflowY = 'auto';
    
    bodyElement.style.overflow = 'visible';
    bodyElement.style.overflowX = 'hidden';
    bodyElement.style.overflowY = 'auto';
    
    // ヒーローセクションにCSSクラスを追加し、フェードアウトアニメーションを開始
    heroSection.classList.add('hero-hidden');

    // ▼▼▼ 追加 ▼▼▼
    // CSSの transition (1秒) が完了した後、動画をDOMから非表示にする
    setTimeout(() => {
        openingVideo.style.display = 'none';
    }, 1000); // ※この時間はCSSの transition 時間と一致させます
    // ▲▲▲ 追加 ▲▲▲
}
// ビデオの再生が終了したらunlockPage関数を実行
openingVideo.addEventListener('ended', unlockPage);

// (保険) ビデオの読み込みに失敗した場合もロックを解除
openingVideo.addEventListener('error', () => {
    console.log('Video error - unlocking page'); // デバッグ用
    unlockPage();
});

// (さらなる保険) 10秒経過しても動画が終わらない場合は強制的にロック解除
setTimeout(() => {
    if (bodyElement.classList.contains('no-scroll')) {
        console.log('Timeout - force unlocking page'); // デバッグ用
        unlockPage();
    }
}, 10000);