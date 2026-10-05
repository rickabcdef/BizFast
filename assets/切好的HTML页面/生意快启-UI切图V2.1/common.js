// 生意快启 - 公共脚本
document.addEventListener('DOMContentLoaded', function() {
    // 创建粒子背景
    createParticles();
    
    // 数字跳动动画
    animateNumbers();
});

function createParticles() {
    const particlesContainer = document.createElement('div');
    particlesContainer.className = 'particles';
    document.body.appendChild(particlesContainer);
    
    for (let i = 0; i < 30; i++) {
        const particle = document.createElement('div');
        particle.className = 'particle';
        particle.style.left = Math.random() * 100 + '%';
        particle.style.animationDuration = (15 + Math.random() * 10) + 's';
        particle.style.animationDelay = Math.random() * 15 + 's';
        particle.style.width = (2 + Math.random() * 4) + 'px';
        particle.style.height = particle.style.width;
        particle.style.opacity = 0.1 + Math.random() * 0.3;
        particlesContainer.appendChild(particle);
    }
}

function animateNumbers() {
    const numbers = document.querySelectorAll('.big-number[data-target]');
    numbers.forEach(num => {
        const target = parseFloat(num.dataset.target);
        const suffix = num.dataset.suffix || '';
        const duration = 800;
        const start = performance.now();
        
        function update(currentTime) {
            const elapsed = currentTime - start;
            const progress = Math.min(elapsed / duration, 1);
            const easeProgress = 1 - Math.pow(1 - progress, 3);
            const current = target * easeProgress;
            
            if (target % 1 !== 0) {
                num.textContent = current.toFixed(1) + suffix;
            } else {
                num.textContent = Math.round(current) + suffix;
            }
            
            if (progress < 1) {
                requestAnimationFrame(update);
            }
        }
        
        requestAnimationFrame(update);
    });
}

// 工具函数：返回首页
function goHome() {
    window.location.href = '02-首页.html';
}
