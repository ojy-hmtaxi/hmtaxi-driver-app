// 전역 JavaScript 함수

// 원형 프로그레스 바 제어
let progressBar = null;
let progressCircle = null;
let progressText = null;
let progressInterval = null;
let currentProgress = 0;

function initProgressBar() {
    progressBar = document.getElementById('pageProgressBar');
    if (progressBar) {
        progressCircle = progressBar.querySelector('.progress-ring-circle');
        progressText = progressBar.querySelector('.progress-text');
        
        // 원의 둘레 계산 (2 * π * r)
        const radius = 54;
        const circumference = 2 * Math.PI * radius;
        
        // stroke-dasharray와 stroke-dashoffset 설정
        if (progressCircle) {
            progressCircle.style.strokeDasharray = circumference;
            progressCircle.style.strokeDashoffset = circumference;
        }
    }
}

function showProgressBar() {
    if (!progressBar) initProgressBar();
    if (!progressBar) return;
    
    currentProgress = 0;
    progressBar.style.display = 'flex';
    
    // 프로그레스 애니메이션 시작
    if (progressInterval) {
        clearInterval(progressInterval);
    }
    
    // 점진적으로 진행률 증가 (0% -> 90%)
    // 페이지 로드 완료 시 100%로 완료 표시
    progressInterval = setInterval(function() {
        if (currentProgress < 90) {
            currentProgress += 2;
            updateProgress(currentProgress);
        }
    }, 50);
}

function updateProgress(percent) {
    if (!progressCircle || !progressText) return;
    
    const radius = 54;
    const circumference = 2 * Math.PI * radius;
    const offset = circumference - (percent / 100) * circumference;
    
    progressCircle.style.strokeDashoffset = offset;
    progressText.textContent = Math.round(percent) + '%';
}

function hideProgressBar() {
    if (progressInterval) {
        clearInterval(progressInterval);
        progressInterval = null;
    }
    
    // 100%로 완료 표시 후 숨김
    updateProgress(100);
    
    setTimeout(function() {
        if (progressBar) {
            progressBar.style.display = 'none';
        }
        currentProgress = 0;
    }, 300);
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
    
    // 링크 클릭 시 프로그레스 바 표시
    document.addEventListener('click', function(e) {
        const link = e.target.closest('a');
        if (link && link.href && !link.href.startsWith('javascript:') && !link.href.startsWith('#')) {
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

// 페이지 언로드 시 프로그레스 바 표시
window.addEventListener('beforeunload', function() {
    showProgressBar();
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

