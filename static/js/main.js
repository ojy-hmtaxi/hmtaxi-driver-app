// 전역 JavaScript 함수

// 원형 프로그레스 바 제어
let progressBar = null;
let progressCircle = null;
let progressText = null;
let progressInterval = null;
let currentProgress = 0;
let progressStartTime = null;
let minDisplayTime = 2000; // 최소 표시 시간: 2초

function initProgressBar() {
    progressBar = document.getElementById('pageProgressBar');
    if (progressBar) {
        progressCircle = progressBar.querySelector('.progress-ring-circle');
        progressText = progressBar.querySelector('.progress-text');
        
        // 원의 둘레 계산 (2 * π * r)
        // 90px 크기, 반지름 41 (중심 45에서 stroke-width 8 고려)
        const radius = 41;
        const circumference = 2 * Math.PI * radius;
        
        // stroke-dasharray와 stroke-dashoffset 설정
        if (progressCircle) {
            progressCircle.style.strokeDasharray = circumference;
            progressCircle.style.strokeDashoffset = circumference;
        }
    }
}

function showProgressBar() {
    // 로그아웃 중이면 프로그레스 바 표시하지 않음
    if (window.skipProgressBar) {
        return;
    }
    
    if (!progressBar) initProgressBar();
    if (!progressBar) return;
    
    // 이전 인터벌 정리
    if (progressInterval) {
        clearInterval(progressInterval);
        progressInterval = null;
    }
    
    // 초기값 설정
    currentProgress = 0;
    progressStartTime = Date.now(); // 시작 시간 기록
    updateProgress(0); // 0%로 초기화
    progressBar.style.display = 'flex';
    
    // 2초 동안 0% -> 90%까지 진행 (정확히 2초에 90% 도달)
    // 90%를 2000ms에 걸쳐 진행하려면 약 22.22ms마다 1%씩 증가
    const totalSteps = 90; // 0%에서 90%까지
    const duration = 2000; // 2초
    const stepInterval = Math.max(16, Math.floor(duration / totalSteps)); // 최소 16ms (약 22ms)
    
    progressInterval = setInterval(function() {
        if (currentProgress < 90) {
            currentProgress += 1;
            updateProgress(currentProgress);
        } else {
            // 90%에 도달하면 인터벌 정리
            clearInterval(progressInterval);
            progressInterval = null;
        }
    }, stepInterval);
}

// 전역으로 노출 (다른 스크립트에서 사용 가능)
window.showProgressBar = showProgressBar;

function updateProgress(percent) {
    if (!progressCircle || !progressText) return;
    
    // 90px 크기, 반지름 41
    const radius = 41;
    const circumference = 2 * Math.PI * radius;
    const offset = circumference - (percent / 100) * circumference;
    
    progressCircle.style.strokeDashoffset = offset;
    progressText.textContent = Math.round(percent) + '%';
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

// 페이지 전환 감지
document.addEventListener('DOMContentLoaded', function() {
    initProgressBar();
    
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
    
    // 링크 클릭 시 프로그레스 바 표시 (로그아웃 링크 제외)
    document.addEventListener('click', function(e) {
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
                    showProgressBar();
                }
            } catch (err) {
                // URL 파싱 오류 시 무시
            }
        }
    });
});

// 페이지 언로드 시 프로그레스 바 표시 (로그아웃 제외)
window.addEventListener('beforeunload', function() {
    // 로그아웃 중이면 프로그레스 바 표시하지 않음
    if (!window.skipProgressBar) {
        showProgressBar();
    }
});

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

