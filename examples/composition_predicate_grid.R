# Independent generated predicate pins, using the preimplementation R witness.
args<-commandArgs(trailingOnly=TRUE)
here<-normalizePath(args[1]);source(file.path(here,'composition_wave_oracles.R'))
values<-c(NA_real_,-2,0,2,3)
for(a in values) for(b in values) {
 for(op in c('eq','ne','lt','le','gt','ge')) cat('CMP',encode(a),encode(b),op,encode(cx_cmp(a,b,op)),sep='|',fill=TRUE)
 cat('TRUTH',encode(a),encode(B(a)),sep='|',fill=TRUE)
 for(c in values) {
  cat('BOOL',encode(a),encode(b),encode(c),encode(as.numeric((cx_truth(a) & cx_truth(b)) | !cx_truth(c))),sep='|',fill=TRUE)
 }
}
