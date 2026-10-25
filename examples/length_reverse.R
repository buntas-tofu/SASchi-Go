# Original independent DS-028 witness for maintainer review, no live SAS.
args <- commandArgs(trailingOnly=TRUE)
hex <- function(bytes) paste(sprintf('%02x', as.integer(bytes)), collapse='')
unhex <- function(value) {
  if (nchar(value) == 0) return(raw())
  as.raw(strtoi(substring(value, seq(1,nchar(value),2), seq(2,nchar(value),2)),16L))
}
reverse_bytes <- function(bytes) {
  values <- as.integer(bytes)
  if (length(values)<1 || length(values)>32767 || any(values<32 | values>126)) stop('bounded reverse input')
  as.raw(values[length(values):1])
}
if (args[1] == 'cases') {
  rows <- read.csv(args[2], colClasses='character', check.names=FALSE, na.strings=NULL)
  cat('id,value\n')
  for (i in seq_len(nrow(rows))) {
    value <- tryCatch({
      if (rows$kind[i] != 'character') stop('type')
      hex(reverse_bytes(unhex(rows$hex[i])))
    },error=function(e) 'REFUSE')
    cat(rows$id[i],',',value,'\n',sep='')
  }
} else if (args[1] == 'program') {
  # Parse the external program in place. No source or derived output is shipped.
  source <- paste(readLines(args[2], warn=FALSE), collapse='\n')
  source <- gsub('(?s)/\\*.*?\\*/','',source,perl=TRUE)
  chars <- strsplit(source,'',fixed=TRUE)[[1]]
  statements <- character(); current <- ''; quote <- ''; i <- 1L
  while (i <= length(chars)) {
    char <- chars[i]
    if (quote != '') {
      current <- paste0(current,char)
      if (char == quote) {
        if (i<length(chars) && chars[i+1]==quote) { i<-i+1L; current<-paste0(current,chars[i]) } else quote<-''
      }
    } else if (char %in% c("'",'"')) { quote<-char;current<-paste0(current,char)
    } else if (char==';') { statements<-c(statements,trimws(current));current<-''
    } else current<-paste0(current,char)
    i<-i+1L
  }
  if (quote!='' || trimws(current)!='') stop('unterminated source')
  widths <- list(); values <- list(); records <- character(); started<-FALSE; ended<-FALSE
  capture <- function(pattern,text) regmatches(text,regexec(pattern,text,ignore.case=TRUE,perl=TRUE))[[1]]
  for (st in statements[nzchar(statements)]) {
    if (grepl('^data\\s+_null_$',st,ignore.case=TRUE,perl=TRUE) && !started) {started<-TRUE;next}
    if (!started || ended) stop('outside program')
    if (tolower(st)=='run') {ended<-TRUE;next}
    m <- capture('^length\\s+([a-z_][a-z0-9_]*(?:\\s+[a-z_][a-z0-9_]*)*)\\s+\\$\\s*([0-9]+)$',st)
    if (length(m)) {
      ns<-tolower(strsplit(m[2],'\\s+',perl=TRUE)[[1]]);w<-as.integer(m[3])
      if (w<1 || w>32767 || anyDuplicated(ns) || any(ns %in% names(widths))) stop('length')
      for (n in ns) { widths[[n]]<-w;values[[n]]<-as.raw(rep(32L,w)) }
      next
    }
    m <- capture('^([a-z_][a-z0-9_]*)\\s*=\\s*reverse\\s*\\(\\s*([a-z_][a-z0-9_]*)\\s*\\)$',st)
    if (length(m)) {
      n<-tolower(m[2]);origin<-tolower(m[3]);if (is.null(widths[[origin]])) stop('unknown reverse argument')
      bytes<-reverse_bytes(values[[origin]]);if (is.null(widths[[n]])) widths[[n]]<-widths[[origin]]
      w<-widths[[n]];values[[n]]<-head(c(bytes,as.raw(rep(32L,w))),w);next
    }
    m <- capture('^([a-z_][a-z0-9_]*)\\s*=\\s*(["\x27])(.+)\\2$',st)
    if (length(m)) {
      n<-tolower(m[2]);q<-m[3];text<-gsub(paste0(q,q),q,m[4],fixed=TRUE);bytes<-charToRaw(text)
      if (is.null(widths[[n]])) widths[[n]]<-length(bytes)
      w<-widths[[n]];values[[n]]<-head(c(bytes,as.raw(rep(32L,w))),w);next
    }
    m <- capture('^put\\s+([a-z_][a-z0-9_]*)$',st)
    if (length(m)) {
      n<-tolower(m[2]);if (is.null(values[[n]])) stop('unknown put argument')
      value<-trimws(rawToChar(values[[n]]),whitespace=' ')
      if (!nzchar(value) || nchar(value,type='bytes')+1>64) stop('bounded put')
      records<-c(records,paste0(value,' '));next
    }
    stop('unsupported witness statement')
  }
  if (!started || !ended) stop('incomplete witness program')
  for (value in records) cat('RECORD:',hex(charToRaw(value)),'\n',sep='')
} else stop('unknown witness mode')
