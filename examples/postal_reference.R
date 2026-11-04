# Independent base-R extraction of the qualified finite USPS domain.
read_postal_reference <- function(path) {
 stopifnot(file.exists(path),file.info(path)$size==4380487)
 read_entry <- function(name) {con <- unz(path,name,open='rb');on.exit(close(con));rawToChar(readBin(con,what='raw',n=100000000L))}
 shared_xml <- read_entry('xl/sharedStrings.xml')
 parts <- regmatches(shared_xml,gregexpr('<si>.*?</si>',shared_xml,perl=TRUE))[[1]]
 shared <- vapply(parts,function(part) {
  spans <- regmatches(part,gregexpr('<t(?:[[:space:]][^>]*)?>[^<]*</t>',part,perl=TRUE))[[1]]
  paste(gsub('<[^>]*>','',spans,perl=TRUE),collapse='')
 },'')
 codes <- c('01040','19119','19139','19140','19142','19145','27511','33031','33133','33135','33141','33157','33161','33177','90049','91950','92025','92071','92116')
 observations <- setNames(lapply(codes,function(x)character()),codes)
 cell_value <- function(cell) {
  m <- regmatches(cell,regexec('<v>([^<]+)</v>',cell,perl=TRUE))[[1]]
  if(length(m)!=2L)return('')
  if(grepl(' t="s"',cell,fixed=TRUE))shared[as.integer(m[2])+1L] else m[2]
 }
 for(sheet in c('xl/worksheets/sheet1.xml','xl/worksheets/sheet2.xml','xl/worksheets/sheet3.xml')) {
  xml <- read_entry(sheet)
  dcells <- regmatches(xml,gregexpr('<c r="D[0-9]+"[^>]*>.*?</c>',xml,perl=TRUE))[[1]]
  values <- vapply(dcells,cell_value,'')
  numeric <- grepl('^[0-9]{1,5}$',values);values[numeric] <- sprintf('%05d',as.integer(values[numeric]))
  for(index in which(values%in%codes)) {
   row <- sub('^<c r="D([0-9]+)".*','\\1',dcells[index],perl=TRUE)
   state_cell <- regmatches(xml,regexpr(paste0('<c r="K',row,'"[^>]*>.*?</c>'),xml,perl=TRUE))
   state <- cell_value(state_cell);stopifnot(grepl('^[A-Z]{2}$',state))
   observations[[values[index]]] <- c(observations[[values[index]]],state)
  }
 }
 result <- vapply(observations,function(states) {stopifnot(length(states)>0L,length(unique(states))==1L);states[1]},'')
 result
}
