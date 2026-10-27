# DS-036 independent native R division and hex-float exactness, no live SAS.
args <- commandArgs(trailingOnly=TRUE)
cases <- read.csv(args[1],colClasses='character',na.strings=NULL)
bound <- function(kind,text) {
  if(kind!='number') stop('numeric only')
  x <- suppressWarnings(as.numeric(text))
  if(!is.finite(x) || abs(x)>2147483647) stop('finite bounded number required')
  x
}
parts <- function(x) {
  # Exact C99 hex representation, independent of Python Fraction arithmetic.
  h <- strsplit(sprintf('%a',abs(x)),'p',fixed=TRUE)[[1]]
  digits <- sub('^0x','',h[1]); pieces <- strsplit(digits,'.',fixed=TRUE)[[1]]
  fraction <- if(length(pieces)==2L) nchar(pieces[2]) else 0L
  digits <- strsplit(gsub('.','',digits,fixed=TRUE),'',fixed=TRUE)[[1]]
  value <- 0
  for(d in digits) value <- value*16 + match(d,c(as.character(0:9),letters[1:6]))-1
  exponent <- as.numeric(h[2])-4*fraction
  while(value!=0 && value %% 2==0) { value <- value/2; exponent <- exponent+1 }
  c(value,exponent)
}
for(i in seq_len(nrow(cases))) {
  r <- cases[i,]
  answer <- tryCatch({
    a <- bound(r$a_kind,r$a); b <- bound(r$b_kind,r$b)
    if(b==0) stop('zero denominator')
    q <- a/b
    if(!is.finite(q) || abs(q)>2147483647) stop('result range')
    if(a!=0) {
      ap <- parts(a); bp <- parts(b)
      if(ap[1] %% bp[1]!=0 || q==0) stop('non-dyadic or underflow')
      qp <- parts(q)
      if(qp[1]!=ap[1]/bp[1] || qp[2]!=ap[2]-bp[2]) stop('rounded quotient')
    }
    paste0('OK:',sprintf('%.17g',q))
  },error=function(e) 'REFUSE')
  cat(r$id,':',answer,'\n',sep='')
}
