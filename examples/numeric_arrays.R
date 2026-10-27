#!/usr/bin/env Rscript
# Original DS-039 witness. Native R arithmetic and environment-backed bindings.
args <- commandArgs(trailingOnly=TRUE)
value <- function(x) {
  if (length(x)!=1 || !is.numeric(x) || is.nan(x) ||
      (!is.na(x) && (!is.finite(x) || abs(x)>2147483647))) stop("value profile")
  x
}
add <- function(a,b,subtract=FALSE) {
  a<-value(a); b<-value(b)
  if (is.na(a) || is.na(b)) return(NA_real_)
  if (subtract) b <- -b
  s <- value(a+b)
  # Knuth TwoSum exposes the binary64 rounding residual, independently of
  # Python's exact-rational implementation. All accepted residuals are zero.
  z <- s-a
  err <- (a-(s-z))+(b-z)
  if (err!=0) stop("rounded addition")
  s
}
ofsum <- function(xs) {
  if (length(xs)<1 || length(xs)>1024) stop("size profile")
  total <- NA_real_
  for (x in xs) {
    x <- value(x)
    if (!is.na(x)) total <- if(is.na(total)) x else add(total,x)
  }
  if (all(is.na(xs))) NA_real_ else sum(xs,na.rm=TRUE)
}
index <- function(i,lo,n) {
  lo<-as.double(lo); n<-as.double(n)
  if (any(!is.finite(c(lo,n))) || lo!=trunc(lo) || n!=trunc(n) ||
      n<1 || n>1024 || lo < -2147483647 || lo+n-1 > 2147483647) stop("bounds")
  i<-value(i)
  if(is.na(i) || i!=trunc(i) || i<lo || i>=lo+n) stop("subscript")
  i-lo
}
decode <- function(kind,text) {
  if(kind=="missing") return(NA_real_)
  if(kind=="number") return(suppressWarnings(as.numeric(text)))
  if(kind=="boolean") return(TRUE)
  if(kind=="character") return(text)
  list()
}
if(args[1]=="alias") {
  env<-new.env(parent=emptyenv()); names<-c("first","second","third")
  for(n in names) assign(n,NA_real_,env)
  getcell<-function(i) get(names[index(i,0,3)+1],env)
  setcell<-function(i,v) assign(names[index(i,0,3)+1],value(v),env)
  assign("first",3,env); setcell(1,5)
  mirror<-getcell(0)
  if(getcell(1)>3) setcell(2,add(getcell(0),getcell(1)))
  total<-ofsum(vapply(names,get,numeric(1),envir=env))
  cat(paste(c(getcell(0),getcell(1),getcell(2),mirror,total,NA),collapse="|"),"\n",sep="")
  assign("first",11,env); reverse<-getcell(0)
  cat(paste(c(getcell(0),getcell(1),getcell(2),mirror,total,reverse),collapse="|"),"\n",sep="")
} else if(args[1]=="cases") {
  d<-read.csv(args[2],stringsAsFactors=FALSE,na.strings=NULL)
  for(j in seq_len(nrow(d))) {
    row<-d[j,]
    result<-tryCatch({
      a<-decode(row$a_kind,row$a); b<-decode(row$b_kind,row$b)
      answer<-switch(row$operation,
        value=value(a), index=index(a,row$lower,row$size),
        add=add(a,b), subtract=add(a,b,TRUE),
        sum={
          fields<-strsplit(row$values,"|",fixed=TRUE)[[1]]
          xs<-vapply(fields,function(x) if(x=="M") NA_real_ else as.numeric(x),numeric(1))
          ofsum(xs)
        }, stop("unknown operation"))
      paste0("OK:",if(is.na(answer)) "M" else sprintf("%a",answer))
    },error=function(e) "REFUSE")
    cat(row$id,":",result,"\n",sep="")
  }
} else stop("unknown scenario")
