# Independent whole-original-fixture witness, authored before source executor.
args <- commandArgs(trailingOnly=TRUE)
lines <- readLines(args[1],warn=FALSE)
payload <- which(lines=="cards;"); stopifnot(length(payload)==1L)
end <- which(seq_along(lines)>payload & lines==";")[1]
outside <- c(lines[seq_len(payload)],lines[seq.int(end,length(lines))])
grammar <- c("data dates;","infile cards;",
 "input id sex :$1. amount born :date9. hired :date9.;","cards;",";","run;",
 "proc format;","value cohort low-'31DEC1959'd=[weekdate37.]",
 "'01JAN1960'd-'31DEC1999'd=[worddate20.]","'01JAN2000'd-high='New era';",
 "run;","title 'Dates';","proc print data=dates;","format born hired cohort.;",
 "run;","title;")
stopifnot(identical(outside,grammar))
cards <- if (end==payload+1L) character() else lines[seq.int(payload+1L,end-1L)]
months <- c("JAN","FEB","MAR","APR","MAY","JUN","JUL","AUG","SEP","OCT","NOV","DEC")
epoch <- as.Date("1960-01-01")
date_read <- function(text) {
 if (text==".") return(NA_real_)
 stopifnot(grepl("^[0-9]{2}[A-Za-z]{3}[0-9]{4}$",text))
 month <- match(toupper(substr(text,3,5)),months);stopifnot(!is.na(month))
 iso <- sprintf("%s-%02d-%s",substr(text,6,9),month,substr(text,1,2))
 date <- as.Date(iso);stopifnot(!is.na(date),format(date,"%Y-%m-%d")==iso)
 as.numeric(date-epoch)
}
integer_read <- function(text) if(text==".") NA_real_ else {
 stopifnot(grepl("^[+-]?[0-9]+$",text));as.numeric(text)
}
rows <- lapply(cards,function(card) {
 fields <- strsplit(trimws(card)," +")[[1]];stopifnot(length(fields)==5L,nchar(fields[2])==1L)
 list(id=integer_read(fields[1]),sex=fields[2],amount=integer_read(fields[3]),
      born=date_read(fields[4]),hired=date_read(fields[5]))
})
invisible(Sys.setlocale("LC_TIME","C"))
cohort <- function(value) {
 if(is.na(value)) return(".")
 date <- epoch+value
 if(date>=as.Date("2000-01-01")) return("New era")
 text <- paste0(format(date,"%B")," ",as.integer(format(date,"%d")),", ",format(date,"%Y"))
 if(date<=as.Date("1959-12-31")) text <- paste0(format(date,"%A"),", ",text)
 text
}
number <- function(value) if(is.na(value)) "." else sprintf("%.0f",value)
quoted <- function(value) paste0('"',value,'"')
report <- c("TITLE: Dates","obs id sex amount born hired")
for(i in seq_along(rows)) {
 r <- rows[[i]]
 report <- c(report,paste(i,number(r$id),quoted(r$sex),number(r$amount),quoted(cohort(r$born)),quoted(cohort(r$hired))))
}
dir.create(args[2],recursive=FALSE)
writeLines(report,file.path(args[2],"print_01.txt"),useBytes=TRUE)
numeric <- function(value) if(is.na(value)) "M" else sprintf("%.0f",value)
table <- vapply(rows,function(r) paste(numeric(r$id),r$sex,numeric(r$amount),numeric(r$born),numeric(r$hired),sep="|"),"")
writeLines(table,file.path(args[2],"rows.txt"),useBytes=TRUE)
language <- sum(grepl(";$",outside))-1L
writeLines(paste(c(language,1L,length(rows)+1L,length(rows),5L,1L),collapse="|"),
 file.path(args[2],"accounting.txt"),useBytes=TRUE)
