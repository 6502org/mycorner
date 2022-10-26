all: clean
	python3 collect.py
	rm -rf combined/
	python3 combine.py

clean:
	rm -f database.sqlite3
	rm -rf combined/

serve: all
	python3 -m http.server 8000 --directory combined/
	open https://localhost:8000

.PHONY: all clean serve
