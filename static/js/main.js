// 전역 JavaScript 함수

/**
 * 로딩 오버레이 및 원형 프로그레스 바 제어
 */
const LoadingManager = {
    overlay: null,
    container: null,
    isActive: false,
    
    /**
     * 초기화
     */
    init() {
        this.overlay = document.getElementById('loadingOverlay');
        this.container = document.getElementById('mainContainer');
        
        if (!this.overlay || !this.container) {
            console.warn('Loading overlay or container not found');
        }
    },
    
    /**
     * 로딩 오버레이 표시
     */
    show() {
        if (this.isActive || !this.overlay) return;
        
        this.isActive = true;
        this.overlay.style.display = 'flex';
        
        // 페이지 전환 플래그 설정 (새 페이지에서 슬라이드 인 애니메이션을 위해)
        sessionStorage.setItem('pageTransition', 'true');
        
        // 즉시 표시 (모바일에서 빠른 페이지 전환 대응)
        this.overlay.classList.add('show');
        
        // 강제 리플로우로 즉시 렌더링
        void this.overlay.offsetHeight;
    },
    
    /**
     * 로딩 오버레이 숨김 및 페이지 슬라이드 인
     */
    hide() {
        if (!this.isActive || !this.overlay || !this.container) return;
        
        // 오버레이 숨김
        this.overlay.classList.remove('show');
        
        // 페이지 슬라이드 인 애니메이션 시작 (약간의 지연 후)
        setTimeout(() => {
            if (this.container) {
                this.container.classList.add('slide-in-from-right');
            }
        }, 100);
        
        setTimeout(() => {
            this.overlay.style.display = 'none';
            this.isActive = false;
            
            // 애니메이션 완료 후 클래스 제거
            if (this.container) {
                setTimeout(() => {
                    this.container.classList.remove('slide-in-from-right');
                }, 400);
            }
        }, 300);
    }
};

/**
 * 페이지 전환 감지 및 이벤트 핸들러 설정
 */
document.addEventListener('DOMContentLoaded', function() {
    // 로딩 매니저 초기화
    LoadingManager.init();
    
    // 페이지 로드 완료 시 로딩 오버레이 숨김 및 슬라이드 인 애니메이션
    LoadingManager.hide();
    LoadingManager.initSlideIn();
    
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
    
    // 폼 제출 시 로딩 오버레이 표시 및 버튼 상태 변경
    const forms = document.querySelectorAll('form');
    forms.forEach(form => {
        form.addEventListener('submit', function(e) {
            const submitButton = form.querySelector('button[type="submit"]');
            if (submitButton && !submitButton.disabled) {
                submitButton.disabled = true;
                submitButton.textContent = '처리 중...';
            }
            
            // 로그아웃 폼은 제외
            const formAction = form.getAttribute('action') || form.action || '';
            if (!formAction.includes('/logout')) {
                // 즉시 표시 (페이지 전환 전에 보이도록)
                LoadingManager.show();
            }
        });
    });
    
    // 링크 클릭 시 로딩 오버레이 표시 (로그아웃 링크 제외)
    document.addEventListener('click', function(e) {
        const link = e.target.closest('a');
        if (link && link.href && !link.href.startsWith('javascript:') && !link.href.startsWith('#')) {
            // 로그아웃 링크는 제외
            if (link.id === 'logoutBtn' || link.href.includes('/logout')) {
                return;
            }
            
            // 같은 도메인 내 링크만
            try {
                const linkUrl = new URL(link.href, window.location.origin);
                const currentUrl = new URL(window.location.href);
                if (linkUrl.origin === currentUrl.origin) {
                    LoadingManager.show();
                }
            } catch (err) {
                // URL 파싱 오류 시 무시
            }
        }
    });
});

// 즉시 초기화 (DOMContentLoaded 전에도 작동하도록)
(function() {
    LoadingManager.init();
    
    // 폼 제출 이벤트를 즉시 등록 (DOMContentLoaded 전에도 작동)
    document.addEventListener('submit', function(e) {
        const form = e.target;
        if (form.tagName === 'FORM') {
            const submitButton = form.querySelector('button[type="submit"]');
            if (submitButton && !submitButton.disabled) {
                submitButton.disabled = true;
                submitButton.textContent = '처리 중...';
            }
            
            // 로그아웃 폼은 제외
            const formAction = form.getAttribute('action') || form.action || '';
            if (!formAction.includes('/logout')) {
                LoadingManager.show();
            }
        }
    }, true); // capture phase에서 실행하여 더 빠르게 처리
})();

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

