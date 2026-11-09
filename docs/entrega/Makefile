# make  (desde esta carpeta) o  make -C docs/entrega  (desde la raíz) genera los PDF.
PDFS := $(patsubst %.typ,%.pdf,$(filter-out tema.typ,$(wildcard *.typ)))

.PHONY: all
all: $(PDFS)

%.pdf: %.typ tema.typ
	typst compile --root ../.. --font-path fuentes $<
