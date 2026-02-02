// file: static/js/main.js

document.addEventListener('DOMContentLoaded', function() {
    
    // =========================================================
    // 1. СТАБИЛЬНОСТЬ И ИНДИКАТОР СВЯЗИ (НОВОЕ)
    // =========================================================
    // Проверяем, подключена ли библиотека socket.io
    if (typeof io !== 'undefined') {
        // Инициализируем сокет
        const socket = io();
        
        // Получаем элементы интерфейса
        const banner = document.getElementById('connection-lost-banner');
        // Находим все кнопки отправки (и в песочнице, и в олимпиаде)
        const submitButtons = document.querySelectorAll('button[type="submit"], .btn-submit');

        // Функция блокировки/разблокировки интерфейса
        function setInterfaceState(enabled) {
            submitButtons.forEach(btn => {
                btn.disabled = !enabled;
            });
            if (banner) {
                banner.style.display = enabled ? 'none' : 'block';
            }
        }

        socket.on('connect', function() {
            console.log("Connected to server (SocketIO)");
            setInterfaceState(true); // Всё ок, прячем баннер, включаем кнопки
        });

        socket.on('disconnect', function() {
            console.warn("Disconnected from server");
            setInterfaceState(false); // Показываем красную плашку, блокируем кнопки
        });

        socket.on('connect_error', function() {
            console.warn("Socket connection error");
            setInterfaceState(false);
        });
    }

    // =========================================================
    // 2. ИНИЦИАЛИЗАЦИЯ CODEMIRROR (СУЩЕСТВУЮЩЕЕ)
    // =========================================================
    
    const codeTextArea = document.getElementById('code');

    // Если на странице нет редактора (например, страница логина),
    // то код ниже выполнять не нужно, но логику сокетов выше мы уже запустили.
    if (!codeTextArea) {
        return; 
    }

    const editor = CodeMirror.fromTextArea(codeTextArea, {
        lineNumbers: true,
        mode: "python", // Язык по умолчанию
        theme: "material-darker",
        matchBrackets: true,
        indentUnit: 4
    });

    // --- СМЕНА ЯЗЫКА ДЛЯ ПОДСВЕТКИ СИНТАКСИСА ---
    const languageSelect = document.getElementById('language');
    if (languageSelect) {
        languageSelect.addEventListener('change', () => {
            const newMode = languageSelect.value === 'C++' ? 'text/x-c++src' : 'python';
            editor.setOption("mode", newMode);
        });
    }

    // =========================================================
    // 3. ОБРАБОТКА ФОРМЫ "ПЕСОЧНИЦЫ" (/run_code)
    // =========================================================
    const submissionForm = document.getElementById('submission-form');
    
    if (submissionForm) {
        submissionForm.addEventListener('submit', function(event) {
            event.preventDefault();

            const form = event.target;
            const taskId = form.task_id.value;
            const language = form.language.value;
            const code = editor.getValue(); 
            const resultsContainer = document.getElementById('results-container');
            const spinner = document.getElementById('spinner');
            const submitButton = form.querySelector('button[type="submit"]');
            
            if (!taskId || !code) {
                alert('Пожалуйста, выберите задачу и введите код.');
                return;
            }

            spinner.classList.remove('d-none');
            submitButton.disabled = true;
            resultsContainer.innerHTML = '';

            fetch('/run_code', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    task_id: taskId,
                    language: language,
                    code: code,
                }),
            })
            .then(response => response.json())
            .then(data => {
                spinner.classList.add('d-none');
                submitButton.disabled = false;
                
                if (data.error) {
                    resultsContainer.innerHTML = `<div class="alert alert-danger">${data.error}</div>`;
                    return;
                }

                const overallStatus = data.passed_count === data.total_tests ? 'success' : 'danger';
                let resultsHTML = `
                    <div class="alert alert-${overallStatus}">
                        <h4 class="alert-heading">Результат: ${data.passed_count} из ${data.total_tests} тестов пройдено.</h4>
                    </div>
                `;

                data.details.forEach(test => {
                    let testResultClass = 'border-secondary';
                    let testHeaderClass = 'bg-light';
                    let statusIcon = `<span class="badge bg-secondary">${test.verdict}</span>`;
        
                    if (test.verdict === 'Accepted') {
                        testResultClass = 'border-success';
                        testHeaderClass = 'bg-success-subtle';
                        statusIcon = `<span class="badge bg-success">${test.verdict}</span>`;
                    } else if (test.verdict === 'Wrong Answer') {
                        testResultClass = 'border-warning';
                        testHeaderClass = 'bg-warning-subtle';
                        statusIcon = `<span class="badge bg-warning text-dark">${test.verdict}</span>`;
                    } else if (test.verdict !== 'Accepted') {
                        testResultClass = 'border-danger';
                        testHeaderClass = 'bg-danger-subtle';
                        statusIcon = `<span class="badge bg-danger">${test.verdict}</span>`;
                    }

                    resultsHTML += `
                        <div class="card mb-3 ${testResultClass}">
                            <div class="card-header ${testHeaderClass}">
                                <strong>Тест ${test.test_num}</strong> ${statusIcon}
                            </div>
                            <div class="card-body">
                                <div class="row">
                                    <div class="col-md-6">
                                        <h6>Входные данные:</h6>
                                        <pre class="bg-light p-2 rounded code-area">${test.input || '(пусто)'}</pre>
                                        <h6>Ожидаемый вывод:</h6>
                                        <pre class="bg-light p-2 rounded code-area">${test.expected}</pre>
                                    </div>
                                    <div class="col-md-6">
                                        <h6>Вывод программы:</h6>
                                        <pre class="bg-light p-2 rounded code-area">${test.output}</pre>
                                        ${test.error && test.error.trim() ? `
                                        <h6>Ошибка выполнения:</h6>
                                        <pre class="bg-danger-subtle text-danger p-2 rounded code-area">${test.error}</pre>
                                        ` : ''}
                                    </div>
                                </div>
                            </div>
                        </div>
                    `;
                });
                resultsContainer.innerHTML = resultsHTML;
            })
            .catch(error => {
                spinner.classList.add('d-none');
                submitButton.disabled = false;
                resultsContainer.innerHTML = `<div class="alert alert-danger">Произошла ошибка сети: ${error}</div>`;
            });
        });
    }
});