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

function updateTaskStatus(taskId, newStatus) {
    console.log("Updating task status:", taskId, newStatus);
    fetch("/update-task-status/", {
        method: "POST",
        headers: {
            "Content-Type": "application/x-www-form-urlencoded",
            "X-CSRFToken": getCSRFToken(),
        },
        body: `task_id=${taskId.replace('task-', '')}&new_status=${capitalizeStatus(newStatus)}`
    })
    .then(response => response.json())
    .then(data => {
        if (!data.success) {
            alert("Failed to update task status: " + data.error);
        } else {
            if (capitalizeStatus(newStatus) === "Completed") {
                const task = document.getElementById(taskId);
                if (task) {
                    task.classList.add("completed");
                    task.setAttribute("draggable", "false");
                }
            }
        }
    });
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

window.drop = function (event, columnId) {
    // console.log("Dropping task into column:", columnId);
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

function columnHasTasks(column) {
    return column.querySelectorAll(".task-card").length > 0;
}

function ensureNoTasksMessage(column) {
    if (!columnHasTasks(column)) {
        // Only add if not present
        if (!column.querySelector('.no-tasks-message')) {
            const msg = document.createElement('p');
            msg.className = 'no-tasks-message';
            msg.textContent = 'No tasks';
            column.appendChild(msg);
        }
    }
}

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
