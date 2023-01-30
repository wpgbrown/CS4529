# ---------------------------------------------------------------------------
#
#  Makefile for ProjectPlan.tex, sample Latex template for project reports
#
#  Dave Ritchie 28/10/02
#
#  On raven, you will probably need "setup tex" in your .login file
#
#  Usage: "make" to make the Postscript, 
#         "make bib" to update the bibliography (needs to re-run latex)
#
# ---------------------------------------------------------------------------

all:	pdf bib

ps:	ProjectPlan.ps

pdf:	ProjectPlan.pdf

bib:	ProjectPlan.bbl

ProjectPlan.eps: ProjectPlan.fig
	fig2dev -L eps ProjectPlan.fig ProjectPlan.eps

ProjectPlan.dvi:	ProjectPlan.tex ProjectPlan.eps
	latex ProjectPlan.tex

ProjectPlan.bbl:	ProjectPlan.bib ProjectPlan.dvi
	bibtex ProjectPlan; \
	latex ProjectPlan;  \
	latex ProjectPlan;

ProjectPlan.ps:	ProjectPlan.dvi
	dvips -Pwww -o ProjectPlan.ps ProjectPlan.dvi

ProjectPlan.pdf:	ProjectPlan.ps ProjectPlan.bbl
	ps2pdf ProjectPlan.ps ProjectPlan.pdf

clean:	
	rm -f *.log *.aux *.dvi *.toc *.blg *.bbl

vclean:	clean
	rm -f *.eps *.ps *.pdf
