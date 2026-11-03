var wms_layers = [];


        var lyr_GoogleTerrain_0 = new ol.layer.Tile({
            'title': 'Google Terrain',
            'type':'base',
            'opacity': 1.000000,
            
            
            source: new ol.source.XYZ({
            attributions: '<a href="https://www.google.at/permissions/geoguidelines/attr-guide.html">Map data ©2015 Google</a>',
                url: 'https://mt1.google.com/vt/lyrs=p&x={x}&y={y}&z={z}'
            })
        });

        var lyr_GoogleSatellite_1 = new ol.layer.Tile({
            'title': 'Google Satellite',
            'type':'base',
            'opacity': 1.000000,
            
            
            source: new ol.source.XYZ({
            attributions: '<a href="https://www.google.at/permissions/geoguidelines/attr-guide.html">Map data ©2015 Google</a>',
                url: 'https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}'
            })
        });
var format__2 = new ol.format.GeoJSON();
var features__2 = format__2.readFeatures(json__2, 
            {dataProjection: 'EPSG:4326', featureProjection: 'EPSG:3857'});
var jsonSource__2 = new ol.source.Vector({
    attributions: ' ',
});
jsonSource__2.addFeatures(features__2);
var lyr__2 = new ol.layer.Vector({
                declutter: false,
                source:jsonSource__2, 
                style: style__2,
                popuplayertitle: 'พื้นที่โครงการ',
                interactive: false,
                title: '<img src="styles/legend/_2.png" /> พื้นที่โครงการ'
            });
var format__3 = new ol.format.GeoJSON();
var features__3 = format__3.readFeatures(json__3, 
            {dataProjection: 'EPSG:4326', featureProjection: 'EPSG:3857'});
var jsonSource__3 = new ol.source.Vector({
    attributions: ' ',
});
jsonSource__3.addFeatures(features__3);
var lyr__3 = new ol.layer.Vector({
                declutter: false,
                source:jsonSource__3,
maxResolution:70.0111653806549,
 
                style: style__3,
                popuplayertitle: 'ขอบเขตตำบล',
                interactive: false,
                title: '<img src="styles/legend/_3.png" /> ขอบเขตตำบล'
            });
var format__4 = new ol.format.GeoJSON();
var features__4 = format__4.readFeatures(json__4, 
            {dataProjection: 'EPSG:4326', featureProjection: 'EPSG:3857'});
var jsonSource__4 = new ol.source.Vector({
    attributions: ' ',
});
jsonSource__4.addFeatures(features__4);
var lyr__4 = new ol.layer.Vector({
                declutter: false,
                source:jsonSource__4, 
                style: style__4,
                popuplayertitle: 'สถานีตรวจวัดอากาศ/ความชื้น',
                interactive: true,
    title: 'สถานีตรวจวัดอากาศ/ความชื้น<br />\
    <img src="styles/legend/_4_0.png" /> สำนักงานเกษตรอำเภอเปือยน้อย<br />\
    <img src="styles/legend/_4_1.png" /> อะโวคาโด<br />\
    <img src="styles/legend/_4_2.png" /> มะม่วงเขียวเสวย<br />\
    <img src="styles/legend/_4_3.png" /> มะม่วงน้ำดอกไม้<br />\
    <img src="styles/legend/_4_4.png" /> มะม่วงน้ำดอกไม้<br />\
    <img src="styles/legend/_4_5.png" /> มะม่วงน้ำดอกไม้<br />' });
var group_ = new ol.layer.Group({
                                layers: [lyr__3,],
                                fold: 'open',
                                title: 'ขอบเขตปกครอง'});

lyr_GoogleTerrain_0.setVisible(true);lyr_GoogleSatellite_1.setVisible(true);lyr__2.setVisible(true);lyr__3.setVisible(true);lyr__4.setVisible(true);
var layersList = [lyr_GoogleTerrain_0,lyr_GoogleSatellite_1,lyr__2,group_,lyr__4];
lyr__2.set('fieldAliases', {'PROV_NAM_T': 'PROV_NAM_T', });
lyr__3.set('fieldAliases', {'TAM_NAM_T': 'TAM_NAM_T', 'AMPHOE_T': 'AMPHOE_T', 'PROV_NAM_T': 'PROV_NAM_T', });
lyr__4.set('fieldAliases', {'Name': 'Name', 'no': 'no', });
lyr__2.set('fieldImages', {'PROV_NAM_T': 'TextEdit', });
lyr__3.set('fieldImages', {'TAM_NAM_T': 'TextEdit', 'AMPHOE_T': 'TextEdit', 'PROV_NAM_T': 'TextEdit', });
lyr__4.set('fieldImages', {'Name': 'TextEdit', 'no': 'Range', });
lyr__2.set('fieldLabels', {'PROV_NAM_T': 'no label', });
lyr__3.set('fieldLabels', {'TAM_NAM_T': 'no label', 'AMPHOE_T': 'no label', 'PROV_NAM_T': 'no label', });
lyr__4.set('fieldLabels', {'Name': 'inline label - always visible', 'no': 'no label', });
lyr__4.on('precompose', function(evt) {
    evt.context.globalCompositeOperation = 'normal';
});