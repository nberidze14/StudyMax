# StudyMax

StudyMax არის სასწავლო ვებ აპლიკაცია, რომელიც აერთიანებს flashcards-ს, notes-ს, to-do list-ს, Pomodoro timer-ს და exams planning-ს ერთ სივრცეში.

## კოდის სტრუქტურა

- `app.py` შეიცავს Flask routes-ს, database helper functions-ს, flashcard review scheduling-ს და გვერდების მთავარ ლოგიკას.
- `schema.sql` განსაზღვრავს SQLite მონაცემთა ბაზების table-ებს.
- `templates/` შეიცავს HTML გვერდებს.
- `static/style.css` შეიცავს ვებ აპლიკაციის სტილებს.
- `studymax.db` ინახავს ლოკალურ demo data-ს.
- `smoke_test.py` ამოწმებს მთავარ გვერდებს და ძირითად workflows-ს დროებითი test database-ით.

მთავარი Python ფაილი სექციებად არის დაყოფილი: database setup, date helpers, flashcard review logic, shared data, Dashboard, Flashcards, To-dos, Notes, Pomodoro და Exams.

## აპლიკაციის გაშვება

შექმენით და გააქტიურეთ virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

დააყენეთ Flask და საჭირო dependencies:

```powershell
pip install -r requirements.txt
```

გაუშვით ვებ აპლიკაცია:

```powershell
python app.py
```

შემდეგ გახსენით ბრაუზერში:

```text
http://127.0.0.1:5000
```

## ტესტირება

Smoke test-ის გასაშვებად გამოიყენეთ:

```powershell
python smoke_test.py
```

ეს ამოწმებს მთავარ გვერდებს, flashcards-ს, review scheduling-ს, notes-to-flashcards ფუნქციას, to-dos-ს, Pomodoro settings-ს და exam study flow-ს. ტესტი იყენებს დროებით მონაცემთა ბაზას.

## Contribution Guidelines

- ახალი Flask route დაამატეთ `app.py` ფაილის შესაბამის სექციაში.
- ახალი HTML გვერდი დაამატეთ `templates/` folder-ში და გამოიყენეთ `base.html`.
- ახალი style დაამატეთ `static/style.css` ფაილში არსებული naming style-ის დაცვით.
- თუ მონაცემთა ბაზის სტრუქტურა იცვლება, განაახლეთ `schema.sql` და შესაბამისი schema helper logic.
- ცვლილებების შემდეგ გაუშვით `python smoke_test.py`.

## License

პროექტი შექმნილია სასწავლო და აკადემიური მიზნებისთვის, როგორც ინდივიდუალური პროექტი.
