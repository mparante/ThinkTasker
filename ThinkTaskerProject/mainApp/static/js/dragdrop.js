window.drag = function (event) {
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
        column.appendChild(task);
    }
};

document.addEventListener("DOMContentLoaded", function () {
    const columns = document.querySelectorAll(".column");

    columns.forEach(column => {
        column.addEventListener("dragover", allowDrop);
        column.addEventListener("drop", function (event) {
            drop(event, this.id);
        });
    });
});

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
