# Independent canonical DATE9 and complete-name date-field witness.
args <- commandArgs(trailingOnly=TRUE)
cases <- read.csv(args[1], stringsAsFactors=FALSE, colClasses="character",
                  na.strings=NULL, check.names=FALSE)
invisible(Sys.setlocale("LC_TIME", "C"))
epoch <- as.Date("1960-01-01")
lower <- as.numeric(as.Date("1753-01-01")-epoch)
upper <- as.numeric(as.Date("3999-12-31")-epoch)
months <- c("JAN","FEB","MAR","APR","MAY","JUN","JUL","AUG","SEP","OCT","NOV","DEC")
refuse <- function() stop("outside canonical date foundations", call.=FALSE)
hex <- function(value) paste(sprintf("%02x", as.integer(charToRaw(value))), collapse="")
read9 <- function(kind, text) {
  if (kind != "text") refuse()
  if (text == ".") return(NA_real_)
  if (!grepl("^[0-9]{2}[A-Za-z]{3}[0-9]{4}$", text)) refuse()
  day <- as.integer(substr(text,1,2)); month <- match(toupper(substr(text,3,5)),months)
  year <- as.integer(substr(text,6,9))
  if (is.na(month) || year<1753 || year>3999) refuse()
  iso <- sprintf("%04d-%02d-%02d",year,month,day)
  date <- suppressWarnings(tryCatch(as.Date(iso), error=function(e) NA))
  if (is.na(date) || format(date,"%Y-%m-%d") != iso) refuse()
  as.numeric(date-epoch)
}
field <- function(row) {
  if (row$fmt_kind != "text" || row$width_kind != "int") refuse()
  name <- tolower(row$fmt); width <- suppressWarnings(as.numeric(row$width))
  if (!is.finite(width) || width != trunc(width) ||
      !(name %in% c("weekdate","worddate"))) refuse()
  if ((name=="weekdate" && !(width>=29 && width<=37)) ||
      (name=="worddate" && !(width>=18 && width<=32))) refuse()
  if (row$kind=="missing") text <- "." else {
    if (!(row$kind %in% c("int","number"))) refuse()
    value <- suppressWarnings(as.numeric(row$value))
    if (!is.finite(value) || value!=trunc(value) || value<lower || value>upper) refuse()
    date <- epoch+value
    text <- paste0(format(date,"%B")," ",as.integer(format(date,"%d")),", ",format(date,"%Y"))
    if (name=="weekdate") text <- paste0(format(date,"%A"),", ",text)
  }
  if (nchar(text,type="bytes")>width) refuse()
  paste0(strrep(" ",width-nchar(text,type="bytes")),text)
}
for (i in seq_len(nrow(cases))) {
  row <- cases[i,,drop=FALSE]
  answer <- tryCatch({
    if (row$op=="read9") {
      value <- read9(row$kind,row$value)
      if (is.na(value)) "M" else paste0("N:",sprintf("%.0f",value))
    } else if (row$op=="field") paste0("T:",hex(field(row))) else refuse()
  },error=function(e) "REFUSE")
  cat(row$id,answer,sep=":");cat("\n")
}
