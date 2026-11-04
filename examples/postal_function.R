# Independent whole-source character-format, FCMP, DSD, SORT and computed REPORT.
args <- commandArgs(trailingOnly=TRUE);stopifnot(length(args)==2L,!file.exists(args[2]))
input_path <- args[1];output_path <- args[2]
script <- sub('^--file=','',grep('^--file=',commandArgs(),value=TRUE)[1]);folder <- dirname(normalizePath(script))
common <- file.path(folder,'format_oracle_common.R');if(!file.exists(common))common <- file.path('examples','format_oracle_common.R')
source(common);source(file.path(folder,'postal_reference.R'))
reference <- read_postal_reference(Sys.getenv('SASCHI_POSTAL_REFERENCE','/tmp/saschi-postal-reference-20261103/Zip_Locale_Detail.xlsx'))
character_format <- function(text) {
 m <- regmatches(text,regexec('(?s)^value[[:space:]]+\\$([A-Za-z_][A-Za-z0-9_]*)[[:space:]]+(.+)$',text,ignore.case=TRUE,perl=TRUE))[[1]];stopifnot(length(m)==3L)
 remain <- m[3];pending <- list();ranges <- list()
 while(nchar(trimws(remain))) {
  part <- regmatches(remain,regexec("^[[:space:]]*'([0-9]{4})'[[:space:]]*(?:-[[:space:]]*'([0-9]{4})')?[[:space:]]*([,=])[[:space:]]*",remain,perl=TRUE))[[1]];stopifnot(length(part)==4L)
  pending[[length(pending)+1L]] <- list(lo=part[2],hi=if(nzchar(part[3]))part[3] else part[2]);remain <- substring(remain,nchar(part[1])+1L)
  if(part[4]=='=') {
   label <- regmatches(remain,regexec("^'([A-Z]{1,3})'",remain,perl=TRUE))[[1]];stopifnot(length(label)==2L)
   for(item in pending)ranges[[length(ranges)+1L]] <- list(lo=item$lo,hi=item$hi,label=label[2])
   pending <- list();remain <- substring(remain,nchar(label[1])+1L)
  }
 }
 stopifnot(!length(pending));list(name=tolower(m[2]),ranges=ranges)
}
parse_function <- function(block) {
 m <- regmatches(block[1],regexec('^function[[:space:]]+([A-Za-z_][A-Za-z0-9_]*)[[:space:]]*\\([[:space:]]*([A-Za-z_][A-Za-z0-9_]*)[[:space:]]*\\$[[:space:]]*,[[:space:]]*([A-Za-z_][A-Za-z0-9_]*)[[:space:]]*\\$[[:space:]]*\\)[[:space:]]*\\$[[:space:]]*5$',block[1],ignore.case=TRUE,perl=TRUE))[[1]];stopifnot(length(m)==4L)
 a <- regmatches(block[2],regexec(paste0("^if[[:space:]]+upcase\\([[:space:]]*",m[3],"[[:space:]]*\\)[[:space:]]*=[[:space:]]*'AU'[[:space:]]+then[[:space:]]+([A-Za-z_][A-Za-z0-9_]*)[[:space:]]*=[[:space:]]*put\\([[:space:]]*",m[4],"[[:space:]]*,[[:space:]]*\\$([A-Za-z_][A-Za-z0-9_]*)\\.[[:space:]]*\\)$"),block[2],ignore.case=TRUE,perl=TRUE))[[1]];stopifnot(length(a)==3L)
 stopifnot(grepl(paste0("^else[[:space:]]+if[[:space:]]+upcase\\([[:space:]]*",m[3],"[[:space:]]*\\)[[:space:]]*=[[:space:]]*'US'[[:space:]]+then[[:space:]]+",a[2],"[[:space:]]*=[[:space:]]*zipstate\\([[:space:]]*",m[4],"[[:space:]]*\\)$"),block[3],ignore.case=TRUE,perl=TRUE))
 stopifnot(grepl(paste0("^else[[:space:]]+",a[2],"[[:space:]]*=[[:space:]]*' '$"),block[4],ignore.case=TRUE,perl=TRUE))
 stopifnot(grepl(paste0('^return[[:space:]]*\\([[:space:]]*',a[2],'[[:space:]]*\\)$'),block[5],ignore.case=TRUE,perl=TRUE),tolower(block[6])=='endsub')
 list(name=tolower(m[2]),format=tolower(a[3]))
}
callback <- function(country,code,ranges) {
 country <- toupper(sub(' +$','',country));code <- sub(' +$','',code)
 if(country=='US') {
  stopifnot(grepl('^[0-9]{5}$',code),code%in%names(reference));result <- reference[[code]]
 } else if(country=='AU') {
  stopifnot(grepl('^[0-9]{4}$',code));result <- NULL
  for(item in ranges)if(code>=item$lo && code<=item$hi) {result <- item$label;break}
  stopifnot(!is.null(result))
 } else result <- ''
 paste0(result,strrep(' ',5L-nchar(result)))
}
texts <- vapply(statements,function(s)s$text,'');norm <- tolower(gsub('[[:space:]]+',' ',texts));payloads <- Filter(function(e)e$kind=='opaque_data',events)
formats <- list();functions <- list();tables <- list();reports <- list();trace <- list();title <- NULL;library <- NULL;active <- NULL;i <- 1L;pi <- 1L;steps <- 0L;inputs <- 0L;producers <- 0L;calls <- 0L;titles <- 0L;sorts <- 0L;bygroups <- 0L
add <- function(value)trace[[length(trace)+1L]] <<- value
while(i<=length(texts)) {
 if(norm[i]=='proc format') {
  value <- character_format(texts[i+1L]);stopifnot(norm[i+2L]=='run');formats[[value$name]] <- value$ranges;add(paste('postal_format',value$name,length(value$ranges),sep='|'));i <- i+3L;steps <- steps+1L
 } else if(startsWith(norm[i],'proc fcmp ')) {
  m <- regmatches(texts[i],regexec('^proc[[:space:]]+fcmp[[:space:]]+outlib[[:space:]]*=[[:space:]]*(work\\.functions)\\.([A-Za-z_][A-Za-z0-9_]*)$',texts[i],ignore.case=TRUE,perl=TRUE))[[1]];stopifnot(length(m)==3L)
  value <- parse_function(texts[(i+1L):(i+6L)]);stopifnot(!is.null(formats[[value$format]]),norm[i+7L]=='quit');functions[[value$name]] <- value$format;library <- tolower(m[2]);i <- i+8L;steps <- steps+1L
  add(paste('postal_function',value$name,value$format,sep='|'));add(paste('postal_library',library,tolower(m[3]),sep='|'))
 } else if(startsWith(norm[i],'options ')) {
  m <- regmatches(texts[i],regexec('^options[[:space:]]+cmplib[[:space:]]*=[[:space:]]*(work\\.functions)$',texts[i],ignore.case=TRUE,perl=TRUE))[[1]];stopifnot(length(m)==2L,tolower(m[2])==library);active <- library;add(paste('postal_cmplib',active,sep='|'));i <- i+1L;steps <- steps+1L
 } else if(startsWith(norm[i],'data ')) {
  name <- tolower(sub('^data[[:space:]]+','',texts[i],ignore.case=TRUE));stopifnot(grepl("^infile[[:space:]]+cards[[:space:]]+dlm[[:space:]]*=[[:space:]]*','[[:space:]]+dsd$",texts[i+1L],ignore.case=TRUE,perl=TRUE),norm[i+3L]=='cards',norm[i+4L]=='run')
  remain <- sub('^input[[:space:]]+','',texts[i+2L],ignore.case=TRUE);schema <- list()
  while(nchar(trimws(remain))) {
   m <- regmatches(remain,regexec('^[[:space:]]*([A-Za-z_][A-Za-z0-9_]*)[[:space:]]*:[[:space:]]*\\$[[:space:]]*([0-9]+)\\.',remain,ignore.case=TRUE,perl=TRUE))[[1]];stopifnot(length(m)==3L);schema[[tolower(m[2])]] <- list(type='character',length=as.integer(m[3]));remain <- substring(remain,nchar(m[1])+1L)
  }
  rows <- lapply(payloads[[pi]]$records,function(record) {
   table <- read.csv(text=record,header=FALSE,colClasses='character',na.strings=NULL,strip.white=FALSE,check.names=FALSE)
   stopifnot(nrow(table)==1L,ncol(table)==length(schema));row <- list()
   for(k in seq_along(schema)) {value <- table[[k]][1];width <- schema[[k]]$length;stopifnot(nchar(value)>0L,nchar(value)<=width);row[[names(schema)[k]]] <- paste0(value,strrep(' ',width-nchar(value)))}
   row
  });pi <- pi+1L;tables[[name]] <- list(schema=schema,rows=rows)
  for(j in seq_along(rows)) {add(paste('postal_input',name,j,1,sep='|'));add(paste('postal_output',name,j,sep='|'))}
  add(paste('postal_input',name,length(rows)+1L,0,sep='|'));producers <- producers+1L;inputs <- inputs+as.integer(length(rows));steps <- steps+1L;i <- i+5L
 } else if(startsWith(norm[i],'proc sort ')) {
  m <- regmatches(texts[i],regexec('^proc[[:space:]]+sort[[:space:]]+data[[:space:]]*=[[:space:]]*([A-Za-z_][A-Za-z0-9_]*)$',texts[i],ignore.case=TRUE,perl=TRUE))[[1]];stopifnot(length(m)==2L,norm[i+2L]=='run');name <- tolower(m[2]);key <- sub('^by[[:space:]]+','',norm[i+1L]);rows <- tables[[name]]$rows
  order <- order(vapply(rows,function(row)row[[key]],''),method='radix');tables[[name]]$rows <- rows[order];add(paste('postal_sort',name,key,length(order),sep='|'))
  for(j in seq_along(order))add(paste('postal_sort_row',j,order[j],sep='|'));sorts <- sorts+1L;steps <- steps+1L;i <- i+3L
 } else if(startsWith(norm[i],'proc report ')) {
  stopifnot(active==library);m <- regmatches(texts[i],regexec('^proc[[:space:]]+report[[:space:]]+data[[:space:]]*=[[:space:]]*([A-Za-z_][A-Za-z0-9_]*)[[:space:]]+nowd$',texts[i],ignore.case=TRUE,perl=TRUE))[[1]];stopifnot(length(m)==2L);name <- tolower(m[2])
  cols <- strsplit(sub('^columns?[[:space:]]+','',norm[i+1L]),'[[:space:]]+')[[1]];by <- sub('^by[[:space:]]+','',norm[i+2L])
  d <- regmatches(texts[i+3L],regexec("^define[[:space:]]+([A-Za-z_][A-Za-z0-9_]*)[[:space:]]*/[[:space:]]*computed[[:space:]]+'((?:[^']|'')*)'$",texts[i+3L],ignore.case=TRUE,perl=TRUE))[[1]];stopifnot(length(d)==3L);computed <- tolower(d[2]);label <- gsub("''","'",d[3],fixed=TRUE)
  stopifnot(grepl(paste0('^compute[[:space:]]+',computed,'[[:space:]]*/[[:space:]]*char[[:space:]]+length[[:space:]]*=[[:space:]]*5$'),texts[i+4L],ignore.case=TRUE,perl=TRUE),norm[i+6L]=='endcomp')
  c <- regmatches(texts[i+5L],regexec(paste0('^',computed,'[[:space:]]*=[[:space:]]*([A-Za-z_][A-Za-z0-9_]*)[[:space:]]*\\([[:space:]]*([A-Za-z_][A-Za-z0-9_]*)[[:space:]]*,[[:space:]]*([A-Za-z_][A-Za-z0-9_]*)[[:space:]]*\\)$'),texts[i+5L],ignore.case=TRUE,perl=TRUE))[[1]];stopifnot(length(c)==4L);fn <- tolower(c[2]);ck <- tolower(c[3]);pc <- tolower(c[4]);i <- i+7L
  if(grepl('^title([[:space:]]|$)',norm[i])) {
   title <- if(norm[i]=='title')NULL else gsub("''","'",sub("^title[[:space:]]+'(.*)'$",'\\1',texts[i],ignore.case=TRUE,perl=TRUE),fixed=TRUE);titles <- titles+1L;i <- i+1L
   add(if(is.null(title))'postal_title|reset' else paste0('postal_title|set|',hex(title)))
  }
  stopifnot(norm[i]=='run');i <- i+1L;steps <- steps+1L;ordinal <- as.integer(length(reports)+1L);table <- tables[[name]]
  header <- paste(vapply(cols,function(col)json_string(if(col==computed)label else col),''),collapse=' ');lines <- if(is.null(title))character() else paste0('TITLE: ',title);lines <- c(lines,header);previous <- NULL
  add(paste('postal_report',name,ordinal,length(table$rows),sep='|'));add(paste0('postal_header|',hex(header)))
  for(j in seq_along(table$rows)) {
   row <- table$rows[[j]]
   if(is.null(previous)||row[[by]]!=previous) {previous <- row[[by]];line <- paste0('BY ',by,'=',json_string(sub(' +$','',previous)));lines <- c(lines,line);add(paste0('postal_by|',hex(line)));bygroups <- bygroups+1L}
   value <- callback(row[[ck]],row[[pc]],formats[[functions[[fn]]]]);calls <- calls+1L
   add(paste0('postal_callback|',fn,'|',hex(row[[ck]]),'|',hex(row[[pc]]),'|',hex(value)))
   line <- paste(vapply(cols,function(col)json_string(sub(' +$','',if(col==computed)value else row[[col]])),''),collapse=' ');lines <- c(lines,line);add(paste0('postal_report_row|',ordinal,'|',j,'|',hex(line)))
  }
  key <- sprintf('report_%02d.txt',ordinal);reports[[key]] <- paste0(paste(lines,collapse='\n'),'\n');add(paste('postal_artifact',key,nchar(reports[[key]],type='bytes'),sep='|'))
 } else if(grepl('^title([[:space:]]|$)',norm[i])) {
  title <- if(norm[i]=='title')NULL else gsub("''","'",sub("^title[[:space:]]+'(.*)'$",'\\1',texts[i],ignore.case=TRUE,perl=TRUE),fixed=TRUE);titles <- titles+1L;steps <- steps+1L;i <- i+1L
  add(if(is.null(title))'postal_title|reset' else paste0('postal_title|set|',hex(title)))
 } else stop('unconsumed independent postal source')
}
result <- list(datasets=tables,log=list());if(length(reports))result$reports <- reports
accounting <- list(language_statements=as.integer(length(statements)),opaque_payloads=producers,steps=steps,input_records=inputs,input_attempts=inputs+producers,formats=as.integer(length(formats)),functions=as.integer(length(functions)),callback_calls=calls,sorts=sorts,by_groups=bygroups,title_sets=titles,reports=as.integer(length(reports)),statement_lines=lapply(statements,function(s)as.integer(s$line)))
dir.create(output_path,recursive=TRUE);write_json('result.json',result);write_json('accounting.json',accounting);write_json('trace.json',trace)
