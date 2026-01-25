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
        // requestAnimationFrame 제거하고 즉시 표시
        this.overlay.classList.add('show');
        
        // 강제 리플로우로 즉시 렌더링
        void this.overlay.offsetHeight;
        
        // 스피너 애니메이션 강제 시작
        this.ensureAnimation();
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
        
        // 이미지가 로드되었는지 확인 (모바일에서 즉시 시작)
        if (spinnerImage.complete && spinnerImage.naturalHeight !== 0) {
            // 이미지가 완전히 로드됨
            this.startRotationAnimation(spinnerImage);
        } else {
            // 이미지 로드 대기 (하지만 애니메이션은 즉시 시작)
            this.startRotationAnimation(spinnerImage);
            
            // 이미지 로드 완료 후 재확인
            spinnerImage.addEventListener('load', () => {
                this.startRotationAnimation(spinnerImage);
            }, { once: true });
            
            // 이미지 로드 실패 시에도 애니메이션은 계속
            spinnerImage.addEventListener('error', () => {
                console.warn('Spinner image failed to load');
                // 이미지가 없어도 애니메이션은 유지
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
        // 인라인 스타일 제거하여 CSS 애니메이션이 작동하도록
        imageElement.style.animation = 'none';
        imageElement.style.webkitAnimation = 'none';
        void imageElement.offsetHeight; // 강제 리플로우
        
        // CSS 애니메이션 재시작 (명시적으로 설정)
        requestAnimationFrame(() => {
            requestAnimationFrame(() => {
                // 인라인 스타일 제거하여 CSS가 적용되도록
                imageElement.style.animation = '';
                imageElement.style.webkitAnimation = '';
                imageElement.style.animationPlayState = 'running';
                imageElement.style.webkitAnimationPlayState = 'running';
                
                // 추가 강제 리플로우로 애니메이션 즉시 시작 보장
                void imageElement.offsetHeight;
                
                // 모바일 브라우저에서 애니메이션이 시작되었는지 확인
                const computedStyle = window.getComputedStyle(imageElement);
                const animationName = computedStyle.animationName || computedStyle.webkitAnimationName;
                
                if (animationName === 'none' || animationName === '') {
                    // 애니메이션이 적용되지 않았으면 강제로 재설정
                    imageElement.style.animation = 'rotate 2s linear infinite';
                    imageElement.style.webkitAnimation = 'rotate 2s linear infinite';
                    imageElement.style.animationPlayState = 'running';
                    imageElement.style.webkitAnimationPlayState = 'running';
                }
            });
        });
    }
};

/**
 * 모바일 브라우저 네비게이션 바 숨김 처리
 */
const MobileBrowserUI = {
    /**
     * 뷰포트 높이 조정 (모바일 브라우저 네비게이션 바 제외)
     */
    setViewportHeight() {
        // 동적 뷰포트 높이 설정
        const vh = window.innerHeight * 0.01;
        document.documentElement.style.setProperty('--vh', `${vh}px`);
        
        // 모바일에서 실제 뷰포트 높이 사용
        if (window.innerHeight !== window.visualViewport?.height) {
            const actualHeight = window.visualViewport?.height || window.innerHeight;
            document.documentElement.style.setProperty('--vh', `${actualHeight * 0.01}px`);
        }
    },
    
    /**
     * 스크롤 시 네비게이션 바 숨김 처리
     */
    hideNavigationBar() {
        let lastScrollTop = 0;
        let ticking = false;
        
        const handleScroll = () => {
            if (!ticking) {
                window.requestAnimationFrame(() => {
                    const scrollTop = window.pageYOffset || document.documentElement.scrollTop;
                    
                    // 스크롤 방향에 따라 네비게이션 바 숨김/표시
                    if (scrollTop > lastScrollTop && scrollTop > 50) {
                        // 아래로 스크롤 - 네비게이션 바 숨김
                        document.body.style.paddingBottom = '0px';
                    } else {
                        // 위로 스크롤 - 네비게이션 바 표시 (하지만 여전히 숨김 유지)
                        document.body.style.paddingBottom = '0px';
                    }
                    
                    lastScrollTop = scrollTop;
                    ticking = false;
                });
                ticking = true;
            }
        };
        
        window.addEventListener('scroll', handleScroll, { passive: true });
        window.addEventListener('touchmove', handleScroll, { passive: true });
    },
    
    /**
     * 상태 바 높이 감지 및 상단 여백 설정 (최소화)
     */
    setStatusBarPadding() {
        // iOS Safari에서 safe-area-inset-top 사용 (최소값만)
        const safeAreaTop = parseInt(getComputedStyle(document.documentElement).getPropertyValue('--safe-area-inset-top')) || 0;
        
        // 모바일에서 상태 바 높이 감지 (최소값만 사용)
        const isMobile = window.innerWidth <= 768;
        const statusBarHeight = isMobile ? Math.max(safeAreaTop, 0) : 0;
        
        // body에 상단 여백 설정 (최소값만)
        if (statusBarHeight > 0) {
            document.body.style.paddingTop = `${statusBarHeight}px`;
            document.documentElement.style.setProperty('--status-bar-height', `${statusBarHeight}px`);
        } else {
            document.body.style.paddingTop = '0px';
        }
        
        // container에도 상단 여백 추가 (최소값만)
        const container = document.getElementById('mainContainer');
        if (container && isMobile) {
            const containerPaddingTop = Math.max(5, safeAreaTop);
            container.style.paddingTop = `${containerPaddingTop}px`;
        }
    },
    
    /**
     * 초기화
     */
    init() {
        // 뷰포트 높이 설정
        this.setViewportHeight();
        
        // 상태 바 높이 감지 및 상단 여백 설정
        this.setStatusBarPadding();
        
        // 리사이즈 시 뷰포트 높이 및 상태 바 여백 재설정
        window.addEventListener('resize', () => {
            this.setViewportHeight();
            this.setStatusBarPadding();
        });
        
        // visualViewport API 지원 시 (모바일 브라우저)
        if (window.visualViewport) {
            window.visualViewport.addEventListener('resize', () => {
                this.setViewportHeight();
                this.setStatusBarPadding();
            });
            window.visualViewport.addEventListener('scroll', () => {
                this.setViewportHeight();
            });
        }
        
        // 스크롤 시 네비게이션 바 숨김
        this.hideNavigationBar();
        
        // 페이지 로드 시 뷰포트 높이 및 상태 바 여백 재설정
        window.addEventListener('load', () => {
            this.setViewportHeight();
            this.setStatusBarPadding();
        });
        
        // 모바일에서 전체 화면 모드 강제
        if (window.navigator.standalone || window.matchMedia('(display-mode: standalone)').matches) {
            // PWA 모드에서 이미 전체 화면
            document.body.classList.add('pwa-mode');
        }
    }
};

/**
 * 페이지 전환 감지 및 이벤트 핸들러 설정
 */
document.addEventListener('DOMContentLoaded', function() {
    // 모바일 브라우저 UI 숨김 초기화
    MobileBrowserUI.init();
    
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

/**
 * 모바일 키보드 처리 - 입력 필드가 키보드에 가려지지 않도록
 */
(function() {
    // 로그인 페이지에서만 작동
    if (!document.querySelector('.login-container')) return;
    
    const inputFields = document.querySelectorAll('.login-box input[type="text"], .login-box input[type="password"]');
    
    inputFields.forEach(input => {
        // 포커스 시 (키보드가 올라올 때)
        input.addEventListener('focus', function() {
            // 약간의 지연 후 스크롤 (키보드 애니메이션 완료 대기)
            setTimeout(() => {
                // 입력 필드가 화면에 보이도록 스크롤
                const inputRect = input.getBoundingClientRect();
                const viewportHeight = window.innerHeight || document.documentElement.clientHeight;
                const keyboardHeight = viewportHeight - (window.visualViewport?.height || viewportHeight);
                
                // 입력 필드가 키보드에 가려지는지 확인
                if (inputRect.bottom > (window.visualViewport?.height || viewportHeight) - keyboardHeight) {
                    // 입력 필드가 키보드 위에 보이도록 스크롤
                    const scrollAmount = inputRect.bottom - (window.visualViewport?.height || viewportHeight) + keyboardHeight + 20;
                    
                    // 부모 요소(login-box)를 스크롤하거나, window를 스크롤
                    const loginBox = input.closest('.login-box');
                    if (loginBox) {
                        loginBox.scrollTop += scrollAmount;
                    } else {
                        window.scrollTo({
                            top: window.scrollY + scrollAmount,
                            behavior: 'smooth'
                        });
                    }
                }
            }, 300); // 키보드 애니메이션 대기 시간
        });
        
        // 블러 시 (키보드가 내려갈 때) - 필요시 스크롤 복원
        input.addEventListener('blur', function() {
            // 키보드가 내려가면 자동으로 스크롤이 복원됨
        });
    });
    
    // visualViewport API 지원 시 (모바일 브라우저)
    if (window.visualViewport) {
        window.visualViewport.addEventListener('resize', () => {
            // 키보드가 올라오거나 내려갈 때 입력 필드가 보이도록 조정
            const activeInput = document.activeElement;
            if (activeInput && (activeInput.tagName === 'INPUT' || activeInput.tagName === 'TEXTAREA')) {
                const inputRect = activeInput.getBoundingClientRect();
                const viewportHeight = window.visualViewport.height;
                
                // 입력 필드가 뷰포트 밖에 있으면 스크롤
                if (inputRect.bottom > viewportHeight) {
                    const scrollAmount = inputRect.bottom - viewportHeight + 20;
                    const loginBox = activeInput.closest('.login-box');
                    if (loginBox) {
                        loginBox.scrollTop += scrollAmount;
                    }
                }
            }
        });
    }
})();

