# Original DS-030 byte extraction and assignment witness for maintainer review.
# Repository/base-R evidence only; no live SAS or temporary-width claim.
args <- commandArgs(trailingOnly=TRUE)
hex <- function(bytes) paste(sprintf('%02x',as.integer(bytes)),collapse='')
unhex <- function(text) {
  if (!nzchar(text)) return(raw())
  as.raw(strtoi(substring(text,seq(1,nchar(text),2),seq(2,nchar(text),2)),16L))
}
number <- function(token) {
  if (substr(token,1,2)!='N:') stop('numeric type')
  value <- suppressWarnings(as.numeric(substring(token,3)))
  if (length(value)!=1 || !is.finite(value) || value<1 || value>32767 || value!=floor(value)) stop('bound')
  value
}
rows <- read.delim(args[1],colClasses='character',check.names=FALSE,na.strings=NULL)
cat('id,status,width,raw,stored,length,lengthn,count,compare\n')
for (i in seq_len(nrow(rows))) {
  answer <- tryCatch({
    if (substr(rows$source[i],1,2)!='S:') stop('character type')
    bytes <- unhex(substring(rows$source[i],3)); values <- as.integer(bytes)
    if (length(values)<1 || length(values)>32767 || any(values<32 | values>126)) stop('source')
    start <- number(rows$position[i]); size <- number(rows$length[i])
    if (start+size-1>length(values)) stop('error-state boundary')
    # Independent indexed byte selection and explicit destination storage.
    extracted <- bytes[seq.int(start,length.out=size)]
    width <- as.integer(rows$target[i]); if (width==0) width<-length(bytes)
    if (width<1 || width>32767) stop('target')
    stored <- head(c(extracted,as.raw(rep(32L,width))),width)
    rawtext <- rawToChar(extracted); padded<-paste0(rawtext,strrep(' ',length(bytes)-length(extracted)))
    trailing <- function(x) sub(' +$','',x)
    lens <- function(x) max(1,nchar(trailing(x),type='bytes'))
    lenn <- function(x) nchar(trailing(x),type='bytes')
    count <- function(x) lengths(regmatches(x,gregexpr('Z',x,fixed=TRUE)))
    # Only padding-insensitive consumers are claimed, checked with both models.
    if (lens(rawtext)!=lens(padded) || lenn(rawtext)!=lenn(padded) || count(rawtext)!=count(padded) ||
        (trailing(rawtext)=='Z')!=(trailing(padded)=='Z')) stop('consumer witness')
    paste('OK',length(bytes),hex(extracted),hex(stored),lens(rawtext),lenn(rawtext),count(rawtext),
          as.integer(trailing(rawtext)=='Z'),sep=',')
  },error=function(e) 'REFUSED,,,,,,,')
  cat(rows$id[i],',',answer,'\n',sep='')
}
