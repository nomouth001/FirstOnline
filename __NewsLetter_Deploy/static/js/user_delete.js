// 사용자 삭제 기능 JavaScript
var deleteUserInfo = {};

// 페이지 로드 시 이벤트 리스너 설정
document.addEventListener('DOMContentLoaded', function() {
    // 모든 삭제 버튼에 이벤트 리스너 추가
    var deleteButtons = document.querySelectorAll('button[id^="delete-btn-"]');
    deleteButtons.forEach(function(button) {
        button.addEventListener('click', function() {
            var userId = this.getAttribute('data-user-id');
            var username = this.getAttribute('data-username');
            showDeleteModal(userId, username);
        });
    });
    
    // 삭제 폼 제출 이벤트 리스너
    var deleteForm = document.getElementById('deleteForm');
    if (deleteForm) {
        deleteForm.addEventListener('submit', function(e) {
            if (deleteUserInfo.id) {
                this.action = '/admin/users/' + deleteUserInfo.id + '/delete';
            }
        });
    }
});

function showDeleteModal(userId, username) {
    // 삭제할 사용자 정보 저장
    deleteUserInfo = {
        id: userId,
        username: username
    };
    
    // 모달 메시지 설정
    var message = '정말로 <strong>' + username + '</strong>의 계정을 삭제하시겠습니까?<br><br>';
    message += '이 작업은 다음을 포함한 모든 데이터를 영구적으로 삭제합니다:<br>';
    message += '• 사용자 계정 정보<br>';
    message += '• 종목 리스트<br>';
    message += '• 분석 기록<br>';
    message += '• 기타 관련 데이터';
    
    var deleteMessage = document.getElementById('deleteMessage');
    if (deleteMessage) {
        deleteMessage.innerHTML = message;
    }
    
    // 모달 표시
    var modal = document.getElementById('deleteModal');
    if (modal) {
        modal.style.display = 'block';
    }
}

function closeDeleteModal() {
    var modal = document.getElementById('deleteModal');
    if (modal) {
        modal.style.display = 'none';
    }
    deleteUserInfo = {};
}

// 모달 외부 클릭시 닫기
window.onclick = function(event) {
    var modal = document.getElementById('deleteModal');
    if (event.target == modal) {
        closeDeleteModal();
    }
}; 