const PRIORITY_ORDER = {
    "Urgent": 1,
    "Important": 2,
    "Medium": 3,
    "Low": 4
};

function sortCardsByPriority(column) {
    const cards = Array.from(column.querySelectorAll('.task-card:not(.completed)'));
    cards.sort((a, b) => {
        const aPriority = (a.querySelector('.priority-badge')?.textContent || "Medium");
        const bPriority = (b.querySelector('.priority-badge')?.textContent || "Medium");
        return PRIORITY_ORDER[aPriority] - PRIORITY_ORDER[bPriority];
    });
    cards.forEach(card => column.appendChild(card));
}

window.drop = function (event, columnId) {
    event.preventDefault();
    const taskId = event.dataTransfer.getData("text/plain");
    const task = document.getElementById(taskId);
    const column = document.getElementById(columnId);

    if (task && column) {
        const noTasksMsg = column.querySelector('.no-tasks-message');
        if (noTasksMsg) noTasksMsg.remove();

        column.appendChild(task);
        updateTaskStatus(taskId, columnId);

        sortCardsByPriority(column);

        document.querySelectorAll(".column").forEach(col => ensureNoTasksMessage(col));
    }
};

window.drag = function (event) {
    if (event.target.classList.contains('completed')) {
        event.preventDefault();
        return false;
    }
    event.dataTransfer.setData("text/plain", event.target.id);
    setTimeout(() => event.target.classList.add("hidden"), 0);
};

window.dragEnd = function (event) {
    event.target.classList.remove("hidden");
};

window.allowDrop = function (event) {
    event.preventDefault();
};

window.drop = function (event, columnId) {
    event.preventDefault();
    const taskId = event.dataTransfer.getData("text/plain");
    const task = document.getElementById(taskId);
    const column = document.getElementById(columnId);

    if (task && column) {
        const noTasksMsg = column.querySelector('.no-tasks-message');
        if (noTasksMsg) {
            noTasksMsg.remove();
        }        
        column.appendChild(task);
        updateTaskStatus(taskId, columnId);

        document.querySelectorAll(".column").forEach(col => {
            ensureNoTasksMessage(col);
        });
    }
};

document.addEventListener("DOMContentLoaded", function () {
    const columns = document.querySelectorAll(".column");

    columns.forEach(column => {
        column.addEventListener("dragover", function (event) {
            allowDrop(event);
            column.classList.add("drag-over");
        });

        column.addEventListener("dragleave", function () {
            column.classList.remove("drag-over");
        });

        column.addEventListener("drop", function (event) {
            drop(event, this.id);
            column.classList.remove("drag-over");
        });
    });
});

document.getElementById('searchListInput').addEventListener('input', function() {
    let filter = this.value.toLowerCase();
    let rows = document.querySelectorAll('#taskTable tbody tr');
    rows.forEach(row => {
        let title = row.cells[0]?.textContent.toLowerCase() || '';
        let description = row.cells[1]?.textContent.toLowerCase() || '';
        if (title.includes(filter) || description.includes(filter)) {
            row.style.display = '';
        } else {
            row.style.display = 'none';
        }
    });
});

document.getElementById('searchBoardInput').addEventListener('input', function () {
    let filter = this.value.toLowerCase();
    document.querySelectorAll('.kanban-column .task-card').forEach(card => {
        // Searches title, description, and priority text inside each card
        let text = card.textContent.toLowerCase();
        card.style.display = text.includes(filter) ? '' : 'none';
    });
});

function columnHasTasks(column) {
    return column.querySelectorAll(".task-card").length > 0;
}

function ensureNoTasksMessage(column) {
    if (!columnHasTasks(column)) {
        if (!column.querySelector('.no-tasks-message')) {
            const msg = document.createElement('p');
            msg.className = 'no-tasks-message';
            msg.textContent = 'No tasks';
            column.appendChild(msg);
        }
    }
}

function getCSRFToken() {
    let cookieValue = null,
    name = "csrftoken";
        if (document.cookie && document.cookie !== "") {
            let cookies = document.cookie.split(";");
            for (let i = 0; i < cookies.length; i++) {
                let cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === name + "=") {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
    return cookieValue;
}

function capitalizeStatus(status) {
    if (status === "to-do") return "Open";
    if (status === "ongoing") return "Ongoing";
    if (status === "completed") return "Completed";
    return status.charAt(0).toUpperCase() + status.slice(1);
}

function formatDeadline(dateString) { 
    if (!dateString) return "";

    // Expected format: "YYYY-MM-DD"
    const [year, month, day] = dateString.split('-').map(Number);
    if (!year || !month || !day) return dateString;

    const d = new Date(year, month - 1, day);

    // Get full month name in English
    const monthStr = d.toLocaleString('en-US', { month: 'long' });
    const dayStr = d.getDate().toString().padStart(2, '0');

    return `${monthStr} ${dayStr}`;
}
