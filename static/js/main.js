// 전역 JavaScript 함수

document.addEventListener('DOMContentLoaded', function() {
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
    
    // 폼 제출 확인
    const forms = document.querySelectorAll('form');
    forms.forEach(form => {
        form.addEventListener('submit', function(e) {
            const submitButton = form.querySelector('button[type="submit"]');
            if (submitButton) {
                submitButton.disabled = true;
                submitButton.textContent = '처리 중...';
            }
        });
    });
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

