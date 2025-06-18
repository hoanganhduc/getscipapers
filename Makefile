all:
	git add --all .
	git commit -S -m "Update @ $(shell date +'%Y-%m-%d  %H:%M:%S')"
	git push
