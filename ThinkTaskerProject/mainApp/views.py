from django.shortcuts import render
from django.http import HttpResponse
from django.conf import settings

stubTasks = [
        {
        'id': 1,
        'title': 'Task #1',
        'description': 'This is the description of Task #1',
        'completed': False,
        'ongoing': False,
        'priority': 'High',
        'deadline_date': None,
        },
        {
        'id': 2,
        'title': 'Task #2',
        'description': 'This is the description of Task #2',
        'completed': False,
        'ongoing': True,
        'priority': 'High',
        'deadline_date': None,
        },
        {
        'id': 3,
        'title': 'Task #3',
        'description': 'This is the description of Task #3',
        'completed': False,
        'ongoing': True,
        'priority': 'High',
        'deadline_date': None,
        },
        {
        'id': 4,
        'title': 'Task #4',
        'description': 'This is the description of Task #4',
        'completed': False,
        'ongoing': False,
        'priority': 'High',
        'deadline_date': None,
        },
        {
        'id':53,
        'title': 'Task #5',
        'description': 'This is the description of Task #5',
        'completed': True,
        'ongoing': False,
        'priority': 'High',
        'deadline_date': None,
        },
    ]

def index(request):
    tasks = stubTasks if settings.DEBUG else []
    context = {
        'todo_tasks': [t for t in tasks if not t['completed'] and not t['ongoing']],
        'ongoing_tasks': [t for t in tasks if t['ongoing'] and not t['completed']],
        'completed_tasks': [t for t in tasks if t['completed']],
    }
    return render(request, 'mainApp/index.html', context)
