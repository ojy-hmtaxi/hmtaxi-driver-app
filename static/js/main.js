// 전역 JavaScript 함수

// 원형 프로그레스 바 제어
let progressBar = null;
let progressCircle = null;
let progressText = null;
let progressInterval = null;
let progressAnimationFrame = null;
let currentProgress = 0;
let progressStartTime = null;
let minDisplayTime = 2000; // 최소 표시 시간: 2초
let circumference = 0; // 전역으로 둘레 저장

function initProgressBar() {
    progressBar = document.getElementById('pageProgressBar');
    if (progressBar) {
        progressCircle = progressBar.querySelector('.progress-ring-circle');
        progressText = progressBar.querySelector('.progress-text');
        
        // 원의 둘레 계산 (2 * π * r)
        // 90px 크기, 반지름 41 (중심 45에서 stroke-width 8 고려)
        const radius = 41;
        circumference = 2 * Math.PI * radius;
        
        // stroke-dasharray와 stroke-dashoffset 설정
        if (progressCircle) {
            progressCircle.style.strokeDasharray = circumference;
            progressCircle.style.strokeDashoffset = circumference;
            // transition 제거를 위해 명시적으로 설정
            progressCircle.style.transition = 'none';
        }
    }
}

function showProgressBar() {
    // 로그아웃 중이면 프로그레스 바 표시하지 않음
    if (window.skipProgressBar) {
        return;
    }
    
    // 프로그레스 바 초기화 (반드시 먼저 실행)
    if (!progressBar) {
        initProgressBar();
    }
    
    if (!progressBar || !progressCircle || !progressText) {
        // 초기화가 완료되지 않았으면 재시도
        setTimeout(showProgressBar, 10);
        return;
    }
    
    // 이전 애니메이션 정리
    if (progressInterval) {
        clearInterval(progressInterval);
        progressInterval = null;
    }
    if (progressAnimationFrame) {
        cancelAnimationFrame(progressAnimationFrame);
        progressAnimationFrame = null;
    }
    
    // 초기값 설정
    currentProgress = 0;
    progressStartTime = Date.now(); // 시작 시간 기록
    
    // 프로그레스 바 표시 (강제 리플로우)
    progressBar.style.display = 'flex';
    // 브라우저에 리플로우 강제
    void progressBar.offsetHeight;
    
    // 즉시 0% 표시 (transition 없이)
    if (progressCircle) {
        progressCircle.style.transition = 'none';
        progressCircle.style.strokeDashoffset = circumference;
    }
    if (progressText) {
        progressText.textContent = '0%';
    }
    
    // 2초 동안 0% -> 90%까지 진행
    // requestAnimationFrame과 setInterval을 결합하여 모바일 호환성 향상
    const duration = 2000; // 2초
    const targetProgress = 90;
    const startTime = Date.now();
    const updateInterval = 16; // ~60fps를 위한 16ms 간격
    
    let lastUpdateTime = startTime;
    
    function animate() {
        const now = Date.now();
        const elapsed = now - startTime;
        
        // 최소 16ms마다 업데이트 (60fps)
        if (now - lastUpdateTime >= updateInterval) {
            const progress = Math.min((elapsed / duration) * targetProgress, targetProgress);
            const newProgress = Math.floor(progress);
            
            if (newProgress !== currentProgress) {
                currentProgress = newProgress;
                updateProgress(currentProgress);
            }
            
            lastUpdateTime = now;
        }
        
        if (elapsed < duration && currentProgress < targetProgress) {
            progressAnimationFrame = requestAnimationFrame(animate);
        } else {
            // 90%에 도달
            currentProgress = targetProgress;
            updateProgress(targetProgress);
            progressAnimationFrame = null;
        }
    }
    
    // setInterval을 백업으로 사용 (모바일 브라우저 호환성)
    progressInterval = setInterval(function() {
        const elapsed = Date.now() - startTime;
        const progress = Math.min((elapsed / duration) * targetProgress, targetProgress);
        const newProgress = Math.floor(progress);
        
        if (newProgress !== currentProgress) {
            currentProgress = newProgress;
            updateProgress(currentProgress);
        }
        
        if (progress >= targetProgress) {
            clearInterval(progressInterval);
            progressInterval = null;
            currentProgress = targetProgress;
            updateProgress(targetProgress);
        }
    }, updateInterval);
    
    // requestAnimationFrame 시작
    progressAnimationFrame = requestAnimationFrame(animate);
}

// 전역으로 노출 (다른 스크립트에서 사용 가능)
window.showProgressBar = showProgressBar;

function updateProgress(percent) {
    if (!progressCircle || !progressText) return;
    
    // 둘레가 계산되지 않았으면 계산
    if (!circumference) {
        const radius = 41;
        circumference = 2 * Math.PI * radius;
    }
    
    const offset = circumference - (percent / 100) * circumference;
    
    // transition 없이 즉시 업데이트
    progressCircle.style.transition = 'none';
    progressCircle.style.strokeDashoffset = offset;
    progressText.textContent = Math.round(percent) + '%';
    
    // 강제 리플로우 (모바일 브라우저 호환성)
    void progressCircle.offsetHeight;
}

function hideProgressBar() {
    // 인터벌 정리
    if (progressInterval) {
        clearInterval(progressInterval);
        progressInterval = null;
    }
    
    // 최소 표시 시간 확인
    const elapsedTime = progressStartTime ? Date.now() - progressStartTime : 0;
    const remainingTime = Math.max(0, minDisplayTime - elapsedTime);
    
    // 현재 진행률이 90% 미만이면 90%까지 빠르게 진행
    if (currentProgress < 90) {
        const stepsTo90 = 90 - currentProgress;
        const fastStepInterval = Math.max(10, Math.floor(remainingTime / stepsTo90));
        
        const fastInterval = setInterval(function() {
            if (currentProgress < 90) {
                currentProgress += 1;
                updateProgress(currentProgress);
            } else {
                clearInterval(fastInterval);
            }
        }, fastStepInterval);
        
        // 90%에 도달하거나 남은 시간이 지나면 100%로 완료
        setTimeout(function() {
            clearInterval(fastInterval);
            updateProgress(100);
            
            // 300ms 후 숨김
            setTimeout(function() {
                if (progressBar) {
                    progressBar.style.display = 'none';
                }
                currentProgress = 0;
                progressStartTime = null;
            }, 300);
        }, remainingTime);
    } else {
        // 이미 90% 이상이면 바로 100%로 완료 표시
        setTimeout(function() {
            // 100%로 완료 표시
            updateProgress(100);
            
            // 300ms 후 숨김
            setTimeout(function() {
                if (progressBar) {
                    progressBar.style.display = 'none';
                }
                currentProgress = 0;
                progressStartTime = null;
            }, 300);
        }, remainingTime);
    }
}

// 즉시 초기화 시도 (스크립트 로드 시점)
if (document.readyState === 'loading') {
    // DOM이 아직 로드 중이면 DOMContentLoaded 대기
    document.addEventListener('DOMContentLoaded', function() {
        initProgressBar();
    });
} else {
    // DOM이 이미 로드되었으면 즉시 초기화
    initProgressBar();
}

// 페이지 전환 감지
document.addEventListener('DOMContentLoaded', function() {
    // 이미 초기화되었는지 확인
    if (!progressBar) {
        initProgressBar();
    }
    
    // 페이지 로드 완료 시 프로그레스 바 숨김
    hideProgressBar();
    
    // 숫자만 입력 가능하도록 제한 (사번, 비밀번호 입력 필드)
    const numberInputs = document.querySelectorAll('input[pattern="[0-9]{4}"]');
    numberInputs.forEach(input => {
        input.addEventListener('input', function(e) {
            this.value = this.value.replace(/[^0-9]/g, '');
        });
        
        input.addEventListener('keypress', function(e) {
            if (!/[0-9]/.test(e.key) && !['Backspace', 'Delete', 'Tab', 'Enter'].includes(e.key)) {
                e.preventDefault();
            }
        });
    });
    
    // 알림 메시지 자동 숨김
    const alerts = document.querySelectorAll('.alert');
    alerts.forEach(alert => {
        setTimeout(() => {
            alert.style.opacity = '0';
            setTimeout(() => {
                alert.remove();
            }, 300);
        }, 5000);
    });
    
    // 폼 제출 확인 및 처리 중 텍스트 표시 + 프로그레스 바 표시
    const forms = document.querySelectorAll('form');
    forms.forEach(form => {
        form.addEventListener('submit', function(e) {
            const submitButton = form.querySelector('button[type="submit"]');
            if (submitButton && !submitButton.disabled) {
                submitButton.disabled = true;
                submitButton.textContent = '처리 중...';
            }
            showProgressBar();
        });
    });
    
    // 링크 클릭/터치 시 프로그레스 바 표시 (로그아웃 링크 제외)
    // mousedown/touchstart를 사용하여 더 일찍 트리거
    function handleLinkInteraction(e) {
        const link = e.target.closest('a');
        if (link && link.href && !link.href.startsWith('javascript:') && !link.href.startsWith('#')) {
            // 로그아웃 링크는 제외 (모달이 표시되므로)
            if (link.id === 'logoutBtn' || link.href.includes('/logout')) {
                return;
            }
            
            // 같은 도메인 내 링크만
            try {
                const linkUrl = new URL(link.href, window.location.origin);
                const currentUrl = new URL(window.location.href);
                if (linkUrl.origin === currentUrl.origin) {
                    // 즉시 프로그레스 바 표시
                    showProgressBar();
                }
            } catch (err) {
                // URL 파싱 오류 시 무시
            }
        }
    }
    
    // mousedown과 touchstart 모두 처리 (모바일 호환성)
    document.addEventListener('mousedown', handleLinkInteraction);
    document.addEventListener('touchstart', handleLinkInteraction);
    
    // click 이벤트도 백업으로 유지
    document.addEventListener('click', handleLinkInteraction);
});

// 페이지 언로드 시 프로그레스 바 표시 (로그아웃 제외)
// beforeunload는 모바일에서 신뢰할 수 없으므로 링크/폼 클릭 시점에 표시
// beforeunload는 제거하고 링크/폼 이벤트에서만 처리

// 근무시작 버튼 클릭 시 확인
function confirmWorkStart() {
    return confirm('근무시작을 기록하시겠습니까?');
}

// 날짜 선택 기능
function selectDate(year, month, day) {
    // 날짜 선택 로직 (필요시 구현)
    console.log('Selected date:', year, month, day);
}

// 근무 상태 업데이트 API 호출
async function updateWorkStatus(day) {
    try {
        const response = await fetch(`/api/work-status/${day}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });
        
        const data = await response.json();
        
        if (data.success) {
            alert(data.message);
            location.reload();
        } else {
            alert(data.message);
        }
    } catch (error) {
        console.error('Error:', error);
        alert('오류가 발생했습니다.');
    }
}

