// [app_name]/static/[app_name]/js/main.js の記述例
document.addEventListener('DOMContentLoaded', function() {
    const openingVideo = document.getElementById('opening-video');
    const header = document.getElementById('page-header');
    const scrollIndicator = document.getElementById('scroll-indicator');

    // 映像が終了したときの処理
    openingVideo.onended = function() {
        header.classList.remove('header-hidden');
        scrollIndicator.classList.remove('scroll-hidden');
    };
});