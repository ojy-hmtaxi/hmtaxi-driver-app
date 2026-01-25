// 전역 JavaScript 함수

/**
 * 로딩 오버레이 및 스피너 제어
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
        requestAnimationFrame(() => {
            this.overlay.classList.add('show');
            // 스피너 애니메이션 강제 시작
            this.ensureAnimation();
        });
    },
    
    /**
     * 로딩 오버레이 숨김
     */
    hide() {
        if (!this.overlay) return;
        
        // 오버레이 숨김
        if (this.isActive) {
            this.overlay.classList.remove('show');
        }
        
        setTimeout(() => {
            if (this.overlay) {
                this.overlay.style.display = 'none';
            }
            this.isActive = false;
        }, 300);
    },
    
    /**
     * 새 페이지 로드 시 슬라이드 인 애니메이션 시작
     */
    initSlideIn() {
        if (!this.container) {
            // 컨테이너가 아직 없으면 재시도
            setTimeout(() => this.initSlideIn(), 10);
            return;
        }
        
        // 페이지 전환이 있었는지 확인
        const hasTransition = sessionStorage.getItem('pageTransition') === 'true';
        
        if (hasTransition) {
            // 플래그 제거
            sessionStorage.removeItem('pageTransition');
            
            // 컨테이너를 초기에 오른쪽에 위치하고 숨김 (즉시 실행)
            this.container.style.transform = 'translateX(100%)';
            this.container.style.opacity = '0';
            
            // 강제 리플로우로 초기 상태 적용
            void this.container.offsetHeight;
            
            // 슬라이드 인 애니메이션 시작
            requestAnimationFrame(() => {
                this.container.classList.add('slide-in-from-right');
                
                // 애니메이션 완료 후 클래스 및 인라인 스타일 제거
                setTimeout(() => {
                    this.container.classList.remove('slide-in-from-right');
                    this.container.style.transform = '';
                    this.container.style.opacity = '';
                }, 400);
            });
        }
    },
    
    /**
     * 스피너 애니메이션 강제 시작
     */
    ensureAnimation() {
        if (!this.overlay) return;
        
        const spinnerImage = this.overlay.querySelector('.progress-spinner-image');
        
        if (!spinnerImage) {
            // 요소가 아직 준비되지 않았으면 재시도
            setTimeout(() => this.ensureAnimation(), 10);
            return;
        }
        
        // 이미지가 로드되었는지 확인
        if (spinnerImage.complete) {
            this.startRotationAnimation(spinnerImage);
        } else {
            spinnerImage.addEventListener('load', () => {
                this.startRotationAnimation(spinnerImage);
            }, { once: true });
        }
    },
    
    /**
     * 회전 애니메이션 시작
     */
    startRotationAnimation(imageElement) {
        // 강제 리플로우
        void imageElement.offsetHeight;
        
        // 애니메이션 재시작 (모바일 호환성 향상)
        imageElement.style.animation = 'none';
        void imageElement.offsetHeight; // 강제 리플로우
        
        // CSS 애니메이션 재시작
        requestAnimationFrame(() => {
            imageElement.style.animation = '';
            imageElement.style.animationPlayState = 'running';
            
            // 추가 강제 리플로우로 애니메이션 즉시 시작 보장
            void imageElement.offsetHeight;
        });
    }
};

/**
 * 페이지 전환 감지 및 이벤트 핸들러 설정
 */
document.addEventListener('DOMContentLoaded', function() {
    // 로딩 매니저 초기화
    if (!LoadingManager.overlay || !LoadingManager.container) {
        LoadingManager.init();
    }
    
    // 페이지 로드 완료 시 로딩 오버레이 숨김
    LoadingManager.hide();
    
    // 페이지 슬라이드 인 애니메이션 시작
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
    
    // 폼 제출 시 버튼 상태 변경
    const forms = document.querySelectorAll('form');
    forms.forEach(form => {
        form.addEventListener('submit', function(e) {
            const submitButton = form.querySelector('button[type="submit"]');
            if (submitButton && !submitButton.disabled) {
                submitButton.disabled = true;
                submitButton.textContent = '처리 중...';
            }
        });
    });
});

// 즉시 초기화 (DOMContentLoaded 전에도 작동하도록)
(function() {
    LoadingManager.init();
    
    // 페이지 전환이 있었는지 확인하고 슬라이드 인 애니메이션 시작
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            LoadingManager.initSlideIn();
        });
    } else {
        LoadingManager.initSlideIn();
    }
    
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
    
    // 링크 클릭 이벤트를 즉시 등록 (DOMContentLoaded 전에도 작동)
    document.addEventListener('click', function(e) {
        const link = e.target.closest('a');
        if (!link) return;
        
        // 로그아웃 링크는 제외
        if (link.id === 'logoutBtn' || link.href.includes('/logout')) {
            return;
        }
        
        // 비활성화된 링크는 제외
        if (link.getAttribute('aria-disabled') === 'true' || 
            link.classList.contains('btn-disabled')) {
            return;
        }
        
        // href가 없거나 javascript:, #로 시작하는 경우 제외
        if (!link.href || link.href.startsWith('javascript:') || link.href === '#') {
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

